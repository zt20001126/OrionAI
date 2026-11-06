"""构造数字人模块独立的输入、模型、工具和输出 LangGraph。"""

from typing import Literal

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.constants import END, START
from langgraph.graph import StateGraph
from langgraph.graph.state import CompiledStateGraph
from pydantic import ValidationError

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
from app.agent.schemas import QuestionPayload
from app.agent.tools.builtin.ask_user_questions import ask_user_questions
from app.agent.tools.registry import ToolRegistry
from app.modules.digital_human.agent.prompts.loader import load_digital_human_prompt
from app.modules.digital_human.agent.state import DigitalHumanState
from app.modules.digital_human.agent.tools.current_date import get_current_date
from app.modules.digital_human.agent.tools.email import prepare_email
from app.modules.digital_human.agent.tools.generate_image import generate_image
from app.modules.digital_human.agent.tools.index_quote import get_index_quote
from app.modules.digital_human.agent.tools.news import get_news
from app.modules.digital_human.agent.tools.reminder import (
    create_reminder,
    get_reminder,
    list_reminders,
)
from app.modules.digital_human.agent.tools.stock_quote import get_stock_quote
from app.modules.digital_human.agent.tools.weather import get_current_weather

DIGITAL_HUMAN_AGENT_CODE = "digital_human"
MAX_INPUT_CHARS = 20_000
RECURSION_LIMIT = 24


def _route_after_agent(
    state: DigitalHumanState,
    *,
    registered_tool_names: frozenset[str],
) -> Literal["tool_node", "output_node"]:
    """模型发起已注册工具调用时进入工具节点，否则输出最终回答。"""

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
        any(
            call.get("name") in {ASK_USER_QUESTIONS_TOOL_NAME, "prepare_email"}
            for call in tool_calls
        )
        and len(tool_calls) != 1
    ):
        raise AgentExecutionError(
            "题卡工具必须单独调用。",
            code="invalid_question_tool_call_batch",
        )
    return "tool_node"


def _route_after_tools(state: DigitalHumanState) -> Literal["agent_node", "pause"]:
    """合法题卡结果结束本轮并等待用户，其余工具结果交回模型。"""

    messages = state.get("messages", [])
    last_message = messages[-1] if messages else None
    return "pause" if _is_question_message(last_message) else "agent_node"


def create_digital_human_graph(
    *,
    chat_model: BaseChatModel,
    checkpointer: BaseCheckpointSaver[object] | None = None,
) -> CompiledStateGraph[DigitalHumanState, object, object, object]:
    """用专属身份编排共享节点；输入为模型和检查点，输出为数字人独立图，供 Runtime 调用。"""

    tool_registry = ToolRegistry(
        [
            ask_user_questions,
            get_current_date,
            get_current_weather,
            generate_image,
            get_stock_quote,
            get_index_quote,
            prepare_email,
            create_reminder,
            list_reminders,
            get_reminder,
            get_news,
        ]
    )
    config = BaseAgentConfig(
        system_prompt=load_digital_human_prompt(tool_registry.names),
        agent=DIGITAL_HUMAN_AGENT_CODE,
        max_input_chars=MAX_INPUT_CHARS,
        recursion_limit=RECURSION_LIMIT,
    )
    graph = StateGraph(DigitalHumanState)
    graph.add_node("input_node", create_input_node(config))
    graph.add_node(
        "agent_node",
        create_agent_node(
            config=config,
            chat_model=chat_model,
            tool_registry=tool_registry,
        ),
    )
    execute_tools = create_tool_node(tool_registry)

    async def execute_digital_human_tools(
        state: DigitalHumanState, config: RunnableConfig
    ) -> dict[str, object]:
        """执行数字人工具，将有效邮件草稿转换为等待用户确认的题卡。"""
        result = await execute_tools(state, config)
        messages = result.get("messages", [])
        for index, message in enumerate(messages):
            if isinstance(message, ToolMessage) and message.name == "prepare_email":
                try:
                    QuestionPayload.model_validate_json(message.content)
                except (ValidationError, ValueError, TypeError):
                    continue
                messages[index] = message.model_copy(update={"name": ASK_USER_QUESTIONS_TOOL_NAME})
        return result

    graph.add_node("tool_node", execute_digital_human_tools)
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
