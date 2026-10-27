"""复用共享对话节点并加入简历候选确认流程。"""

import asyncio
import json
import uuid
from collections.abc import Callable
from typing import Any, Literal

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.constants import END, START
from langgraph.graph import StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agent.config import BaseAgentConfig
from app.agent.errors import AgentInputError
from app.agent.nodes.input import create_input_node
from app.agent.nodes.model import create_agent_node
from app.agent.nodes.output import output_node
from app.agent.nodes.tool import _is_question_message, create_tool_node
from app.agent.tools.builtin.ask_user_questions import ask_user_questions
from app.agent.tools.registry import ToolRegistry
from app.modules.agents.resume_agent.prompts.loader import load_resume_agent_prompt
from app.modules.agents.resume_agent.state import ResumeAgentState
from app.modules.agents.resume_agent.tools import build_optimization_question

RESUME_AGENT_CODE = "resume_assistant"
STAGE_TOOL = "stage_resume_optimization"
QUESTION_TOOL = "ask_user_questions"
_GENERIC_INPUT = create_input_node(BaseAgentConfig(system_prompt="", agent=RESUME_AGENT_CODE))


def build_resume_agent_graph(
    *,
    chat_model: BaseChatModel,
    tools: list[Any],
    resume_writer: Callable[[int, dict[str, Any]], str],
    checkpointer: BaseCheckpointSaver[Any] | None = None,
) -> CompiledStateGraph[Any, Any, Any, Any]:
    config = BaseAgentConfig(system_prompt=load_resume_agent_prompt(), agent=RESUME_AGENT_CODE)
    registry = ToolRegistry([ask_user_questions, *tools])
    graph = StateGraph(ResumeAgentState)
    graph.add_node("input_node", _create_resume_input_node(resume_writer))
    graph.add_node(
        "agent_node",
        create_agent_node(config=config, chat_model=chat_model, tool_registry=registry),
    )
    graph.add_node("tool_node", _create_resume_tool_node(registry))
    graph.add_node("output_node", output_node)
    graph.add_edge(START, "input_node")
    graph.add_conditional_edges(
        "input_node",
        lambda state: "output_node" if state.get("direct_resume_answer") else "agent_node",
        {"output_node": "output_node", "agent_node": "agent_node"},
    )
    graph.add_conditional_edges(
        "agent_node",
        lambda state: _route_after_agent(state, registry.names),
        {"tool_node": "tool_node", "output_node": "output_node"},
    )
    graph.add_conditional_edges(
        "tool_node",
        _route_after_tools,
        {"tool_node": "tool_node", "agent_node": "agent_node", "pause": END},
    )
    graph.add_edge("output_node", END)
    return graph.compile(checkpointer=checkpointer)


def _create_resume_input_node(resume_writer: Callable[[int, dict[str, Any]], str]):
    async def resume_input_node(
        state: ResumeAgentState,
        config: RunnableConfig | None = None,
    ) -> dict[str, Any]:
        await _GENERIC_INPUT(state)
        configurable = dict((config or {}).get("configurable") or {})
        answers = configurable.get("resume_answers")
        candidate = state.get("pending_resume_optimization")
        if not candidate or not isinstance(answers, dict):
            return {"direct_resume_answer": False}
        choice = answers.get("resume_optimization")
        if choice not in {
            "确认采用并保存",
            "重新生成候选",
            "取消本次优化",
            "暂不处理",
        }:
            raise AgentInputError("简历优化确认答案无效。", code="invalid_resume_confirmation")
        if choice == "确认采用并保存":
            user_id = configurable.get("user_id")
            if not isinstance(user_id, int) or user_id <= 0:
                result = "unavailable"
            else:
                result = await asyncio.to_thread(resume_writer, user_id, candidate)
            answer = {
                "saved": "已按你的确认保存优化内容。",
                "resume_changed": (
                    "简历在生成候选后已有更新，未覆盖新内容。"
                    "请重新读取后再生成候选。"
                ),
                "invalid_candidate": "候选内容校验失败，简历没有变化。请重新生成候选。",
                "unavailable": "保存暂时失败，简历没有变化，请稍后重试。",
            }.get(result, "保存暂时失败，简历没有变化，请稍后重试。")
            return _direct_answer(answer)
        if choice == "重新生成候选":
            return {"pending_resume_optimization": None, "direct_resume_answer": False}
        return _direct_answer("已取消本次优化，原简历保持不变。")

    return resume_input_node


def _create_resume_tool_node(registry: ToolRegistry):
    execute = create_tool_node(registry)

    async def resume_tool_node(state: ResumeAgentState, config: RunnableConfig | None = None):
        result = await execute(state, config)
        messages = result.get("messages", [])
        last = messages[-1] if messages else None
        if isinstance(last, ToolMessage) and last.name == STAGE_TOOL:
            candidate = _read_staged_candidate(last.content)
            if candidate is not None:
                question = build_optimization_question(candidate)
                call_id = uuid.uuid4().hex
                question_call = {
                    "name": QUESTION_TOOL,
                    "args": {"questions": [question.model_dump(mode="json")]},
                    "id": call_id,
                    "type": "tool_call",
                }
                return {
                    **result,
                    "messages": [*messages, AIMessage(content="", tool_calls=[question_call])],
                    "pending_resume_optimization": candidate,
                }
        return result

    return resume_tool_node


def _read_staged_candidate(content: object) -> dict[str, Any] | None:
    if not isinstance(content, str):
        return None
    try:
        payload = json.loads(content)
        candidate = payload.get("candidate") if payload.get("success") else None
        if not isinstance(candidate, dict):
            return None
        return candidate
    except (ValueError, AttributeError):
        return None


def _route_after_agent(
    state: ResumeAgentState, tool_names: frozenset[str]
) -> Literal["tool_node", "output_node"]:
    messages = state.get("messages", [])
    last = messages[-1] if messages else None
    if not getattr(last, "tool_calls", None):
        return "output_node"
    unknown = {call.get("name") for call in last.tool_calls} - tool_names
    if unknown:
        raise AgentInputError("模型请求了未注册工具。", code="unregistered_tool_call")
    return "tool_node"


def _route_after_tools(state: ResumeAgentState) -> Literal["tool_node", "agent_node", "pause"]:
    messages = state.get("messages", [])
    last = messages[-1] if messages else None
    if _is_question_message(last):
        return "pause"
    if isinstance(last, AIMessage) and last.tool_calls:
        return "tool_node"
    return "agent_node"


def _direct_answer(answer: str) -> dict[str, Any]:
    return {
        "messages": [AIMessage(content=answer)],
        "answer": answer,
        "pending_resume_optimization": None,
        "direct_resume_answer": True,
        "question_round_count": 0,
    }
