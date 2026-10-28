from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from app.core.config import Settings
from app.infrastructure.database.checkpointer import (
    CHECKPOINTER_SETUP_LOCK_KEY,
    open_checkpointer,
)


class FakeConnection:
    def __init__(self) -> None:
        self.statements: list[tuple[str, tuple[int, ...]]] = []
        self.locked = False

    async def execute(self, statement: str, params: tuple[int, ...]) -> None:
        self.statements.append((statement, params))
        if "pg_advisory_lock" in statement:
            self.locked = True
        elif "pg_advisory_unlock" in statement:
            self.locked = False


class FakeCheckpointer:
    def __init__(self) -> None:
        self.conn = FakeConnection()
        self.setup_called = False

    async def setup(self) -> None:
        assert self.conn.locked
        self.setup_called = True


@pytest.mark.anyio
async def test_open_checkpointer_uses_dedicated_database_and_serializes_setup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(
        database_url="postgresql+psycopg://business:secret@localhost/orionai",
        checkpoint_database_url="postgresql+psycopg://checkpointer:secret@localhost/checkpoint",
    )
    checkpointer = FakeCheckpointer()
    observed_urls: list[str] = []

    @asynccontextmanager
    async def fake_from_conn_string(url: str) -> AsyncIterator[FakeCheckpointer]:
        observed_urls.append(url)
        yield checkpointer

    monkeypatch.setattr(
        AsyncPostgresSaver,
        "from_conn_string",
        staticmethod(fake_from_conn_string),
    )

    async with open_checkpointer(settings) as opened:
        assert opened is checkpointer
        assert checkpointer.setup_called
        assert checkpointer.conn.locked is False

    expected_url = settings.checkpoint_database_url.replace(
        "postgresql+psycopg://", "postgresql://", 1
    )
    assert observed_urls == [expected_url]
    assert checkpointer.conn.statements == [
        ("SELECT pg_advisory_lock(%s)", (CHECKPOINTER_SETUP_LOCK_KEY,)),
        ("SELECT pg_advisory_unlock(%s)", (CHECKPOINTER_SETUP_LOCK_KEY,)),
    ]


@pytest.mark.anyio
async def test_open_checkpointer_requires_dedicated_url() -> None:
    settings = Settings(_env_file=None, checkpoint_database_url="")

    with pytest.raises(ValueError, match="CHECKPOINT_DATABASE_URL"):
        async with open_checkpointer(settings):
            raise AssertionError("连接配置缺失时不得打开 Checkpointer")
