"""校验图状态中的本轮用户文本，通过后不写入多余状态。"""

from collections.abc import Awaitable, Callable

from langchain_core.messages import HumanMessage

from app.agent.config import BaseAgentConfig
from app.agent.errors import AgentInputError
from app.agent.state import ConversationState


def create_input_node(
    config: BaseAgentConfig,
) -> Callable[[ConversationState], Awaitable[dict[str, object]]]:
    """创建输入节点，检查本轮文本类型、空白和长度。"""

    async def input_node(state: ConversationState) -> dict[str, object]:
        messages = state.get("messages", [])
        latest_user_message = next(
            (message for message in reversed(messages) if isinstance(message, HumanMessage)),
            None,
        )
        if latest_user_message is None or not isinstance(latest_user_message.content, str):
            raise AgentInputError("本轮需要提供文本格式的用户消息。", code="invalid_user_message")

        text = latest_user_message.content.strip()
        if not text:
            raise AgentInputError("用户消息不能为空。", code="empty_user_message")
        if len(text) > config.max_input_chars:
            raise AgentInputError("用户消息超过允许的长度。", code="input_too_long")
        return {}

    return input_node
