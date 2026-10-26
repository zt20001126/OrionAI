"""执行注册工具并限制题卡轮数，将内部异常转为安全观察结果。"""

import logging
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from langchain_core.messages import ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.prebuilt import ToolNode
from pydantic import ValidationError

from app.agent.config import MAX_QUESTION_ROUNDS_PER_RUN
from app.agent.schemas import QuestionPayload
from app.agent.state import ConversationState
from app.agent.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)
ASK_USER_QUESTIONS_TOOL_NAME = "ask_user_questions"
TOOL_FAILURE_FEEDBACK = "工具执行失败。请勿编造工具结果，可根据已有信息回答或向用户说明限制。"
QUESTION_ROUND_LIMIT_FEEDBACK = "本轮对话已达到题卡提问上限，请根据已获得的信息继续回答。"


def _handle_tool_error(error: Exception) -> str:
    """仅记录异常类型，并向模型提供统一的工具失败信息。"""

    logger.warning("agent_tool_call_failed error_type=%s", type(error).__name__)
    return TOOL_FAILURE_FEEDBACK


def _is_question_message(message: object) -> bool:
    """仅把通过题卡 schema 校验的提问工具结果视为等待状态。"""

    if not isinstance(message, ToolMessage) or message.name != ASK_USER_QUESTIONS_TOOL_NAME:
        return False
    if not isinstance(message.content, str):
        return False
    try:
        QuestionPayload.model_validate_json(message.content)
    except (ValidationError, ValueError):
        return False
    return True


def create_tool_node(
    tool_registry: ToolRegistry,
) -> Callable[..., Awaitable[dict[str, Any]]]:
    """创建工具执行节点，题卡轮数超限时将限制作为工具观察交回模型。"""

    tool_node = ToolNode(
        list(tool_registry.tools),
        name="tool_node",
        handle_tool_errors=_handle_tool_error,
    )

    async def execute_tools(
        state: ConversationState,
        runnable_config: RunnableConfig | None = None,
    ) -> dict[str, Any]:
        messages = state.get("messages", [])
        last_message = messages[-1] if messages else None
        tool_calls = getattr(last_message, "tool_calls", [])
        question_calls = [
            tool_call
            for tool_call in tool_calls
            if isinstance(tool_call, Mapping)
            and tool_call.get("name") == ASK_USER_QUESTIONS_TOOL_NAME
        ]
        question_round_count = state.get("question_round_count", 0)

        if question_calls and question_round_count >= MAX_QUESTION_ROUNDS_PER_RUN:
            # ToolMessage id 与模型 tool_call id 对应，模型能在下一轮看到受控限制。
            return {
                "messages": [
                    ToolMessage(
                        content=QUESTION_ROUND_LIMIT_FEEDBACK,
                        tool_call_id=str(tool_call.get("id") or ""),
                        name=ASK_USER_QUESTIONS_TOOL_NAME,
                    )
                    for tool_call in question_calls
                ]
            }

        result = await tool_node.ainvoke(state, config=runnable_config)
        result_messages = result.get("messages", [])
        if any(_is_question_message(message) for message in result_messages):
            result["question_round_count"] = question_round_count + 1
        return result

    return execute_tools
