import asyncio
from typing import Any

import pytest

from app.core.config import Settings
from app.modules.conversations.title import (
    MAX_CONVERSATION_TITLE_LENGTH,
    MAX_CONVERSATION_TITLE_SOURCE_LENGTH,
    ModelConversationTitleGenerator,
    fallback_conversation_title,
    normalize_conversation_title,
)


class FakeResponse:
    def __init__(self, content: Any) -> None:
        self.content = content


class FakeModel:
    def __init__(self, response: FakeResponse | Exception) -> None:
        self.response = response
        self.messages: list[Any] = []

    async def ainvoke(self, messages: list[Any]) -> FakeResponse:
        self.messages = messages
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


class SlowModel:
    async def ainvoke(self, _messages: list[Any]) -> FakeResponse:
        await asyncio.sleep(0.05)
        return FakeResponse("太迟的标题")


@pytest.mark.anyio
async def test_title_generator_uses_first_message_and_normalizes_model_output() -> None:
    model = FakeModel(FakeResponse("标题：‘订单查询需求’\n额外说明"))
    generator = ModelConversationTitleGenerator(model, timeout_seconds=1)

    title = await generator.generate_title("帮我设计一个订单查询助手")

    assert title == "订单查询需求"
    assert model.messages[1].content == "帮我设计一个订单查询助手"
    assert "只输出标题本身" in model.messages[0].content


def test_title_normalization_limits_length_and_uses_first_nonempty_line() -> None:
    content = f"\n{'标' * 30}\n其他内容"

    title = normalize_conversation_title(content)

    assert title == "标" * MAX_CONVERSATION_TITLE_LENGTH
    assert len(title or "") <= MAX_CONVERSATION_TITLE_LENGTH
    assert normalize_conversation_title([{"type": "text", "text": "标题：‘新标题’"}]) == "新标题"
    assert normalize_conversation_title({"text": "无效内容"}) is None


@pytest.mark.anyio
async def test_title_generator_truncates_source_and_returns_none_on_model_error() -> None:
    model = FakeModel(FakeResponse("简短标题"))
    generator = ModelConversationTitleGenerator(model, timeout_seconds=1)

    await generator.generate_title("消息" * (MAX_CONVERSATION_TITLE_SOURCE_LENGTH + 10))

    assert len(model.messages[1].content) == MAX_CONVERSATION_TITLE_SOURCE_LENGTH

    failed_generator = ModelConversationTitleGenerator(
        FakeModel(RuntimeError("provider failure")),
        timeout_seconds=1,
    )
    assert await failed_generator.generate_title("一条消息") is None


@pytest.mark.anyio
async def test_title_generator_timeout_returns_none() -> None:
    generator = ModelConversationTitleGenerator(SlowModel(), timeout_seconds=0.005)  # type: ignore[arg-type]

    assert await generator.generate_title("一条消息") is None


def test_fallback_title_collapses_whitespace_and_settings_default_to_eight_seconds() -> None:
    assert fallback_conversation_title("  帮我\n整理   业务  ") == "帮我 整理 业务"
    assert fallback_conversation_title(" \n ") == "新会话"
    assert Settings(_env_file=None).conversation_title_timeout_seconds == 8
