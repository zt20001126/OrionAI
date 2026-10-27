from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import pytest
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from app.core.application import create_agent_lifespan
from app.core.config import Settings
from app.infrastructure.llm.provider import OpenAICompatibleChatModelProvider


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
        deepseek_api_key="test-key",
        deepseek_model="test-model",
    )
    checkpointer = FakeCheckpointer()
    observed_urls: list[str] = []
    seed_sessions: list[object] = []
    agent = object()

    @asynccontextmanager
    async def fake_checkpointer_context(url: str) -> AsyncIterator[FakeCheckpointer]:
        observed_urls.append(url)
        yield checkpointer

    def fake_from_conn_string(url: str) -> Any:
        return fake_checkpointer_context(url)

    monkeypatch.setattr(
        AsyncPostgresSaver,
        "from_conn_string",
        staticmethod(fake_from_conn_string),
    )
    monkeypatch.setattr(
        OpenAICompatibleChatModelProvider,
        "create_chat_model",
        lambda _provider: object(),
    )
    monkeypatch.setattr(
        "app.core.application.create_basic_conversation_agent",
        lambda *, chat_model, checkpointer: agent,
    )
    monkeypatch.setattr(
        "app.core.application.ensure_general_chat_skill",
        lambda session: seed_sessions.append(session),
    )

    application = FakeApplication()
    lifespan = create_agent_lifespan(settings)
    async with lifespan(application):
        assert checkpointer.setup_called
        assert len(seed_sessions) == 1
        assert application.state.conversation_agent is agent

    assert observed_urls == ["postgresql://test:test@localhost/test"]
    assert not hasattr(application.state, "conversation_agent")
