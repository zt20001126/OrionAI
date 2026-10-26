"""将用户、会话和消息主键改为 Snowflake ID，并同步外键及已有 Checkpoint 线程。

Revision ID: 0004_snowflake_primary_ids
Revises: 0003_conversations_messages
Create Date: 2026-10-26
"""

import time
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_snowflake_primary_ids"
down_revision: str | None = "0003_conversations_messages"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# 与运行时 Snowflake 结构一致；worker ID 1023 专用于一次性数据迁移。
_EPOCH_MS = 1_704_067_200_000
_MIGRATION_WORKER_ID = 1023
_SEQUENCE_BITS = 12
_WORKER_ID_SHIFT = 12
_TIMESTAMP_SHIFT = 22
_MAX_SEQUENCE = (1 << _SEQUENCE_BITS) - 1
_MAX_TIMESTAMP_DELTA = (1 << 41) - 1
_TABLES = ("users", "conversations", "messages")
_CHECKPOINT_TABLES = ("checkpoints", "checkpoint_blobs", "checkpoint_writes")


class _MigrationSnowflakeGenerator:
    """迁移内使用的固定算法快照，不依赖会变化的应用代码。"""

    def __init__(self) -> None:
        self._last_timestamp_ms = -1
        self._sequence = 0

    def next_id(self) -> int:
        timestamp_ms = time.time_ns() // 1_000_000
        if timestamp_ms < self._last_timestamp_ms:
            timestamp_ms = self._wait_until_after(self._last_timestamp_ms)

        if timestamp_ms == self._last_timestamp_ms:
            self._sequence = (self._sequence + 1) & _MAX_SEQUENCE
            if self._sequence == 0:
                timestamp_ms = self._wait_until_after(self._last_timestamp_ms)
        else:
            self._sequence = 0

        self._last_timestamp_ms = timestamp_ms
        timestamp_delta = timestamp_ms - _EPOCH_MS
        if timestamp_delta < 0 or timestamp_delta > _MAX_TIMESTAMP_DELTA:
            raise RuntimeError("当前时间超出 Snowflake ID 支持范围。")
        return (
            (timestamp_delta << _TIMESTAMP_SHIFT)
            | (_MIGRATION_WORKER_ID << _WORKER_ID_SHIFT)
            | self._sequence
        )

    @staticmethod
    def _wait_until_after(timestamp_ms: int) -> int:
        current_timestamp_ms = time.time_ns() // 1_000_000
        while current_timestamp_ms <= timestamp_ms:
            time.sleep(0.001)
            current_timestamp_ms = time.time_ns() // 1_000_000
        return current_timestamp_ms


def _id_map(
    connection: sa.Connection,
    table_name: str,
    generator: _MigrationSnowflakeGenerator,
) -> dict[int, int]:
    old_ids = connection.execute(sa.text(f"SELECT id FROM {table_name} ORDER BY id")).scalars()
    return {old_id: generator.next_id() for old_id in old_ids}


def _remap_column(
    connection: sa.Connection,
    table_name: str,
    column_name: str,
    id_mapping: dict[int, int],
) -> None:
    if not id_mapping:
        return
    connection.execute(
        sa.text(f"UPDATE {table_name} SET {column_name} = :new_id WHERE {column_name} = :old_id"),
        [{"old_id": old_id, "new_id": new_id} for old_id, new_id in id_mapping.items()],
    )


def _checkpoint_table_exists(connection: sa.Connection, table_name: str) -> bool:
    return bool(
        connection.scalar(
            sa.text(
                "SELECT EXISTS ("
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema = current_schema() AND table_name = :table_name"
                ")"
            ),
            {"table_name": table_name},
        )
    )


def _remap_checkpoint_threads(
    connection: sa.Connection,
    user_ids: dict[int, int],
    conversation_ids: dict[int, int],
) -> None:
    """若 Checkpointer 表已存在，同步改写内含用户和会话 ID 的 thread_id。"""

    conversation_rows = connection.execute(
        sa.text("SELECT id, user_id FROM conversations ORDER BY id")
    ).all()
    thread_mapping: dict[str, str] = {}
    for conversation_id, user_id in conversation_rows:
        new_conversation_id = conversation_ids[conversation_id]
        new_user_id = user_ids[user_id]
        old_thread_id = f"orionai:{user_id}:basic_conversation_agent:{conversation_id}"
        new_thread_id = f"orionai:{new_user_id}:basic_conversation_agent:{new_conversation_id}"
        thread_mapping[old_thread_id] = new_thread_id

    for table_name in _CHECKPOINT_TABLES:
        if not _checkpoint_table_exists(connection, table_name) or not thread_mapping:
            continue
        connection.execute(
            sa.text(f"UPDATE {table_name} SET thread_id = :new_id WHERE thread_id = :old_id"),
            [
                {"old_id": old_thread_id, "new_id": new_thread_id}
                for old_thread_id, new_thread_id in thread_mapping.items()
            ],
        )


def _drop_conversation_foreign_keys() -> None:
    op.drop_constraint(
        "conversations_user_id_fkey",
        "conversations",
        type_="foreignkey",
    )
    op.drop_constraint(
        "messages_conversation_id_fkey",
        "messages",
        type_="foreignkey",
    )


def _create_conversation_foreign_keys() -> None:
    op.create_foreign_key(
        "conversations_user_id_fkey",
        "conversations",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "messages_conversation_id_fkey",
        "messages",
        "conversations",
        ["conversation_id"],
        ["id"],
        ondelete="CASCADE",
    )


def upgrade() -> None:
    connection = op.get_bind()
    generator = _MigrationSnowflakeGenerator()

    # 暂时解除外键，避免主键回填时拒绝更新；迁移事务会原子提交或回滚。
    _drop_conversation_foreign_keys()
    user_ids = _id_map(connection, "users", generator)
    conversation_ids = _id_map(connection, "conversations", generator)
    message_ids = _id_map(connection, "messages", generator)

    _remap_checkpoint_threads(connection, user_ids, conversation_ids)
    for table_name in _TABLES:
        op.execute(f"ALTER TABLE {table_name} ALTER COLUMN id DROP IDENTITY IF EXISTS")
    op.alter_column("users", "id", comment="用户 Snowflake ID")
    op.alter_column("conversations", "id", comment="会话 Snowflake ID")
    op.alter_column("messages", "id", comment="消息 Snowflake ID")

    _remap_column(connection, "users", "id", user_ids)
    _remap_column(connection, "conversations", "user_id", user_ids)
    _remap_column(connection, "conversations", "id", conversation_ids)
    _remap_column(connection, "messages", "conversation_id", conversation_ids)
    _remap_column(connection, "messages", "id", message_ids)
    _create_conversation_foreign_keys()


def _sequential_id_map(connection: sa.Connection, table_name: str) -> dict[int, int]:
    old_ids = connection.execute(sa.text(f"SELECT id FROM {table_name} ORDER BY id")).scalars()
    return {old_id: index for index, old_id in enumerate(old_ids, start=1)}


def _restore_identity(table_name: str) -> None:
    op.execute(f"ALTER TABLE {table_name} ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY")
    op.execute(
        "SELECT setval("
        f"pg_get_serial_sequence('{table_name}', 'id'), "
        f"COALESCE((SELECT MAX(id) FROM {table_name}), 1), "
        f"EXISTS (SELECT 1 FROM {table_name})"
        ")"
    )


def downgrade() -> None:
    connection = op.get_bind()
    _drop_conversation_foreign_keys()
    user_ids = _sequential_id_map(connection, "users")
    conversation_ids = _sequential_id_map(connection, "conversations")
    message_ids = _sequential_id_map(connection, "messages")

    _remap_checkpoint_threads(connection, user_ids, conversation_ids)
    _remap_column(connection, "users", "id", user_ids)
    _remap_column(connection, "conversations", "user_id", user_ids)
    _remap_column(connection, "conversations", "id", conversation_ids)
    _remap_column(connection, "messages", "conversation_id", conversation_ids)
    _remap_column(connection, "messages", "id", message_ids)

    for table_name in _TABLES:
        op.alter_column(table_name, "id", comment=None)
        _restore_identity(table_name)
    _create_conversation_foreign_keys()
