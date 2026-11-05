"""生成、规范化并回退会话标题。"""

import asyncio
import logging
from typing import Any, Protocol

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from app.agent.prompts.loader import load_conversation_title_prompt

logger = logging.getLogger(__name__)

MAX_CONVERSATION_TITLE_LENGTH = 15
MAX_CONVERSATION_TITLE_SOURCE_LENGTH = 4_000
FALLBACK_CONVERSATION_TITLE = "新会话"


class ConversationTitleGenerator(Protocol):
    """标题生成边界，供 Service 调用并由测试替换。"""

    async def generate_title(self, first_user_message: str) -> str | None: ...


class ModelConversationTitleGenerator:
    """使用注入的对话模型，根据首条用户消息生成标题。"""

    def __init__(self, model: BaseChatModel, timeout_seconds: float) -> None:
        self._model = model
        self._timeout_seconds = timeout_seconds

    async def generate_title(self, first_user_message: str) -> str | None:
        """调用模型并规范结果；模型失败时返回空值供 Service 回退。"""

        source = first_user_message.strip()
        if not source:
            return None

        messages = [
            SystemMessage(content=load_conversation_title_prompt()),
            HumanMessage(content=source[:MAX_CONVERSATION_TITLE_SOURCE_LENGTH]),
        ]
        try:
            async with asyncio.timeout(self._timeout_seconds):
                response = await self._model.ainvoke(messages)
        except TimeoutError:
            logger.warning("conversation_title_generation_timed_out")
            return None
        except Exception as error:
            logger.warning(
                "conversation_title_generation_failed error_type=%s",
                type(error).__name__,
            )
            return None

        return normalize_conversation_title(getattr(response, "content", response))


def normalize_conversation_title(content: Any) -> str | None:
    """只保留模型输出第一条非空行，并清理格式和长度。"""

    if isinstance(content, str):
        text = content
    elif isinstance(content, list):
        text = "".join(
            item if isinstance(item, str) else item["text"]
            for item in content
            if isinstance(item, str)
            or (isinstance(item, dict) and isinstance(item.get("text"), str))
        )
    else:
        return None

    first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
    edge_characters = " \t\r\n\"'“”‘’\x60#"
    title = " ".join(first_line.split()).strip(edge_characters)
    for prefix in ("标题：", "标题:"):
        if title.startswith(prefix):
            title = title[len(prefix) :].strip()
            break
    title = title.strip(edge_characters)[:MAX_CONVERSATION_TITLE_LENGTH].strip()
    return title or None


def fallback_conversation_title(first_user_message: str) -> str:
    """模型无可用结果时，使用压缩空白后的首条消息摘要。"""

    title = " ".join(first_user_message.split())[:MAX_CONVERSATION_TITLE_LENGTH]
    return title or FALLBACK_CONVERSATION_TITLE
