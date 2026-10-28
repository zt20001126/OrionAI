from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest

from app.core.application import create_agent_lifespan
from app.core.config import Settings
from app.infrastructure.llm.provider import OpenAICompatibleChatModelProvider
from app.modules.conversations.title import ModelConversationTitleGenerator


class FakeCheckpointer:
    """记录 Checkpointer 初始化调用，不连接 PostgreSQL。"""

    def __init__(self) -> None:
        self.setup_called = False

    async def setup(self) -> None:
        self.setup_called = True


class FakeApplication:
    """只提供 lifespan 需要的 app.state 容器。"""

    def __init__(self) -> None:
        self.state = type("State", (), {})()


@pytest.mark.anyio
async def test_agent_lifespan_initializes_and_releases_dependencies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(
        database_url="postgresql+psycopg://test:test@localhost/test",
        checkpoint_database_url="postgresql://checkpointer:secret@localhost/checkpoint",
        deepseek_api_key="test-key",
        deepseek_model="test-model",
    )
    checkpointer = FakeCheckpointer()
    observed_urls: list[str] = []
    seed_sessions: list[object] = []
    agent = object()

    @asynccontextmanager
    async def fake_open_checkpointer(
        _settings: Settings,
    ) -> AsyncIterator[FakeCheckpointer]:
        observed_urls.append(_settings.checkpoint_database_url)
        await checkpointer.setup()
        yield checkpointer

    monkeypatch.setattr("app.core.application.open_checkpointer", fake_open_checkpointer)
    monkeypatch.setattr(
        OpenAICompatibleChatModelProvider,
        "create_chat_model",
        lambda _provider: object(),
    )
    monkeypatch.setattr(
        "app.core.application.create_basic_conversation_agent",
        lambda *, chat_model, checkpointer: agent,
    )
    resume_agent = object()
    monkeypatch.setattr("app.core.application.ResumeAgent", lambda **_kwargs: resume_agent)
    monkeypatch.setattr(
        "app.core.application.ensure_general_chat_skill",
        lambda session: seed_sessions.append(session),
    )
    monkeypatch.setattr(
        "app.core.application.ensure_image_agent_skill",
        lambda session: seed_sessions.append(session),
    )
    image_agent = object()
    monkeypatch.setattr("app.core.application.ImageAgent", lambda **_kwargs: image_agent)

    application = FakeApplication()
    lifespan = create_agent_lifespan(settings)
    async with lifespan(application):
        assert checkpointer.setup_called
        assert len(seed_sessions) == 2
        assert application.state.conversation_agent is agent
        assert application.state.agent_registry.get("image_agent") is image_agent
        assert application.state.agent_registry.get("resume_assistant") is resume_agent
        assert isinstance(
            application.state.conversation_title_generator,
            ModelConversationTitleGenerator,
        )
        assert application.state.conversation_title_generator._timeout_seconds == 8

    assert observed_urls == [settings.checkpoint_database_url]
    assert not hasattr(application.state, "conversation_agent")
    assert not hasattr(application.state, "agent_registry")
    assert not hasattr(application.state, "conversation_title_generator")
