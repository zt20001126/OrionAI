"""管理 LangGraph Checkpointer 专用连接及启动时迁移锁。"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from sqlalchemy.engine import make_url

from app.core.config import Settings

# 多个 API Worker 同时启动时，共用此 PostgreSQL 会话级锁串行执行 Checkpointer setup。
CHECKPOINTER_SETUP_LOCK_KEY = 0x4F52494F4E434B50


@asynccontextmanager
async def open_checkpointer(settings: Settings) -> AsyncIterator[AsyncPostgresSaver]:
    """打开 Checkpointer 连接，在持锁状态下检查并应用 LangGraph 自身迁移。"""

    if not settings.checkpoint_database_url.strip():
        raise ValueError("必须配置 CHECKPOINT_DATABASE_URL 才能启动 Agent。")

    checkpoint_url = make_url(settings.checkpoint_database_url)
    if checkpoint_url.drivername not in {"postgresql", "postgresql+psycopg"}:
        raise ValueError("CHECKPOINT_DATABASE_URL 必须指向 PostgreSQL psycopg 连接。")
    connection_string = checkpoint_url.set(drivername="postgresql").render_as_string(
        hide_password=False
    )

    async with AsyncPostgresSaver.from_conn_string(connection_string) as checkpointer:
        await checkpointer.conn.execute(
            "SELECT pg_advisory_lock(%s)", (CHECKPOINTER_SETUP_LOCK_KEY,)
        )
        try:
            await checkpointer.setup()
        finally:
            await checkpointer.conn.execute(
                "SELECT pg_advisory_unlock(%s)", (CHECKPOINTER_SETUP_LOCK_KEY,)
            )
        yield checkpointer
