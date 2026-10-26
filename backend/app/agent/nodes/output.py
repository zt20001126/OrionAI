"""从最终 AI 消息中提取并校验用户可见的文本回答。"""

from collections.abc import Mapping

from langchain_core.messages import AIMessage

from app.agent.errors import AgentExecutionError
from app.agent.state import ConversationState


def _extract_text(content: object) -> str:
    """提取纯文本或文本块，不将非文本模型载荷转成用户回答。"""

    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        text_parts = [
            block["text"]
            for block in content
            if isinstance(block, Mapping)
            and block.get("type") == "text"
            and isinstance(block.get("text"), str)
        ]
        return "\n".join(part.strip() for part in text_parts if part.strip())
    return ""


async def output_node(state: ConversationState) -> dict[str, object]:
    """读取最后一条非工具 AI 消息并输出 answer，完成后重置题卡轮数。"""

    final_message = next(
        (
            message
            for message in reversed(state.get("messages", []))
            if isinstance(message, AIMessage)
        ),
        None,
    )
    if final_message is None or final_message.tool_calls:
        raise AgentExecutionError("没有可作为最终回答的模型消息。", code="missing_final_message")

    answer = _extract_text(final_message.content)
    if not answer:
        raise AgentExecutionError("模型没有生成有效文本回答。", code="empty_final_answer")
    return {"answer": answer, "question_round_count": 0}
