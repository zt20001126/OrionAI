"""构建 input、model、tool 和 output 节点组成的基础对话图。"""

from typing import Any, Literal

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.constants import END, START
from langgraph.graph import StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agent.config import BaseAgentConfig
from app.agent.errors import AgentExecutionError
from app.agent.nodes.input import create_input_node
from app.agent.nodes.model import create_agent_node
from app.agent.nodes.output import output_node
from app.agent.nodes.tool import (
    ASK_USER_QUESTIONS_TOOL_NAME,
    _is_question_message,
    create_tool_node,
)
from app.agent.state import ConversationState
from app.agent.tools.registry import ToolRegistry


def _route_after_agent(
    state: ConversationState,
    *,
    registered_tool_names: frozenset[str],
) -> Literal["tool_node", "output_node"]:
    """模型调用已注册工具时进入工具节点，否则验证并输出最终回答。"""

    messages = state.get("messages", [])
    last_message = messages[-1] if messages else None
    tool_calls = getattr(last_message, "tool_calls", [])
    if not tool_calls:
        return "output_node"
    if not isinstance(last_message, AIMessage):
        raise AgentExecutionError(
            "只有 AI 消息可以发起工具调用。", code="invalid_tool_call_message"
        )

    unknown_names = {
        str(tool_call.get("name", ""))
        for tool_call in tool_calls
        if tool_call.get("name") not in registered_tool_names
    }
    if unknown_names:
        raise AgentExecutionError("模型请求了未注册工具。", code="unregistered_tool_call")
    if (
        any(call.get("name") == ASK_USER_QUESTIONS_TOOL_NAME for call in tool_calls)
        and len(tool_calls) != 1
    ):
        raise AgentExecutionError(
            "题卡工具必须单独调用。",
            code="invalid_question_tool_call_batch",
        )
    return "tool_node"


def _route_after_tools(state: ConversationState) -> Literal["agent_node", "pause"]:
    """合法题卡结果结束本轮并等待用户，其余工具观察交回模型。"""

    messages = state.get("messages", [])
    last_message = messages[-1] if messages else None
    return "pause" if _is_question_message(last_message) else "agent_node"


def build_conversation_graph(
    *,
    config: BaseAgentConfig,
    chat_model: BaseChatModel,
    tool_registry: ToolRegistry,
    checkpointer: BaseCheckpointSaver[Any] | None = None,
) -> CompiledStateGraph[Any, Any, Any, Any]:
    """只从显式注入依赖构建并编译图，不访问环境变量、ORM 或 FastAPI。"""

    graph = StateGraph(ConversationState)
    graph.add_node("input_node", create_input_node(config))
    graph.add_node(
        "agent_node",
        create_agent_node(config=config, chat_model=chat_model, tool_registry=tool_registry),
    )
    graph.add_node("tool_node", create_tool_node(tool_registry))
    graph.add_node("output_node", output_node)
    graph.add_edge(START, "input_node")
    graph.add_edge("input_node", "agent_node")
    graph.add_conditional_edges(
        "agent_node",
        lambda state: _route_after_agent(
            state,
            registered_tool_names=tool_registry.names,
        ),
        {"tool_node": "tool_node", "output_node": "output_node"},
    )
    graph.add_conditional_edges(
        "tool_node",
        _route_after_tools,
        {"agent_node": "agent_node", "pause": END},
    )
    graph.add_edge("output_node", END)
    return graph.compile(checkpointer=checkpointer)
