"""将技能及用户技能关联主键改为 Snowflake ID，并注册简历和文献助手。

Revision ID: 0006_snowflake_skill_ids
Revises: 0005_create_skills
Create Date: 2026-10-27
"""

import time
import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_snowflake_skill_ids"
down_revision: str | None = "0005_create_skills"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_EPOCH_MS = 1_704_067_200_000
_MIGRATION_WORKER_ID = 1023
_SEQUENCE_BITS = 12
_WORKER_ID_SHIFT = 12
_TIMESTAMP_SHIFT = 22
_MAX_SEQUENCE = (1 << _SEQUENCE_BITS) - 1
_MAX_TIMESTAMP_DELTA = (1 << 41) - 1


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


def _add_seed_skills(connection: sa.Connection, generator: _MigrationSnowflakeGenerator) -> None:
    connection.execute(
        sa.text(
            "INSERT INTO skills (id, code, name, description, type, status) "
            "VALUES (:id, :code, :name, :description, :type, :status) "
            "ON CONFLICT (code) DO NOTHING"
        ),
        [
            {
                "id": generator.next_id(),
                "code": "resume_assistant",
                "name": "简历助手",
                "description": "提供简历分析、内容优化、岗位匹配及面试准备等智能服务。",
                "type": "agent",
                "status": "disabled",
            },
            {
                "id": generator.next_id(),
                "code": "literature_assistant",
                "name": "文献助手",
                "description": "提供学术文献解析、内容总结、文献问答及研究信息提取等智能服务。",
                "type": "agent",
                "status": "disabled",
            },
        ],
    )


def upgrade() -> None:
    connection = op.get_bind()
    generator = _MigrationSnowflakeGenerator()
    skill_ids = {
        old_id: generator.next_id()
        for old_id in connection.execute(sa.text("SELECT id FROM skills ORDER BY id")).scalars()
    }
    user_skill_rows = connection.execute(
        sa.text("SELECT id, skill_id FROM user_skills ORDER BY id")
    ).all()
    user_skill_ids = {row.id: generator.next_id() for row in user_skill_rows}

    op.add_column("skills", sa.Column("snowflake_id", sa.BigInteger(), nullable=True))
    op.add_column("user_skills", sa.Column("snowflake_id", sa.BigInteger(), nullable=True))
    op.add_column("user_skills", sa.Column("snowflake_skill_id", sa.BigInteger(), nullable=True))

    if skill_ids:
        connection.execute(
            sa.text("UPDATE skills SET snowflake_id = :new_id WHERE id = :old_id"),
            [{"old_id": old_id, "new_id": new_id} for old_id, new_id in skill_ids.items()],
        )
    if user_skill_rows:
        connection.execute(
            sa.text(
                "UPDATE user_skills "
                "SET snowflake_id = :new_id, snowflake_skill_id = :new_skill_id "
                "WHERE id = :old_id"
            ),
            [
                {
                    "old_id": row.id,
                    "new_id": user_skill_ids[row.id],
                    "new_skill_id": skill_ids[row.skill_id],
                }
                for row in user_skill_rows
            ],
        )

    op.drop_constraint("user_skills_skill_id_fkey", "user_skills", type_="foreignkey")
    op.drop_constraint("uq_user_skills_user_skill", "user_skills", type_="unique")
    op.drop_constraint("user_skills_pkey", "user_skills", type_="primary")
    op.drop_constraint("skills_pkey", "skills", type_="primary")
    op.drop_column("user_skills", "id")
    op.drop_column("user_skills", "skill_id")
    op.drop_column("skills", "id")

    op.alter_column(
        "skills",
        "snowflake_id",
        new_column_name="id",
        existing_type=sa.BigInteger(),
        nullable=False,
    )
    op.alter_column(
        "user_skills",
        "snowflake_id",
        new_column_name="id",
        existing_type=sa.BigInteger(),
        nullable=False,
    )
    op.alter_column(
        "user_skills",
        "snowflake_skill_id",
        new_column_name="skill_id",
        existing_type=sa.BigInteger(),
        nullable=False,
    )

    op.create_primary_key("skills_pkey", "skills", ["id"])
    op.create_primary_key("user_skills_pkey", "user_skills", ["id"])
    op.create_foreign_key(
        "user_skills_skill_id_fkey",
        "user_skills",
        "skills",
        ["skill_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_unique_constraint("uq_user_skills_user_skill", "user_skills", ["user_id", "skill_id"])
    op.alter_column("skills", "id", comment="技能 Snowflake ID")
    op.alter_column("user_skills", "id", comment="用户技能关联 Snowflake ID")

    _add_seed_skills(connection, generator)


def downgrade() -> None:
    connection = op.get_bind()
    skill_ids = {
        old_id: uuid.uuid4()
        for old_id in connection.execute(sa.text("SELECT id FROM skills ORDER BY id")).scalars()
    }
    user_skill_rows = connection.execute(
        sa.text("SELECT id, skill_id FROM user_skills ORDER BY id")
    ).all()
    user_skill_ids = {row.id: uuid.uuid4() for row in user_skill_rows}

    op.add_column("skills", sa.Column("uuid_id", sa.Uuid(), nullable=True))
    op.add_column("user_skills", sa.Column("uuid_id", sa.Uuid(), nullable=True))
    op.add_column("user_skills", sa.Column("uuid_skill_id", sa.Uuid(), nullable=True))
    if skill_ids:
        connection.execute(
            sa.text("UPDATE skills SET uuid_id = :new_id WHERE id = :old_id"),
            [{"old_id": old_id, "new_id": new_id} for old_id, new_id in skill_ids.items()],
        )
    if user_skill_rows:
        connection.execute(
            sa.text(
                "UPDATE user_skills "
                "SET uuid_id = :new_id, uuid_skill_id = :new_skill_id "
                "WHERE id = :old_id"
            ),
            [
                {
                    "old_id": row.id,
                    "new_id": user_skill_ids[row.id],
                    "new_skill_id": skill_ids[row.skill_id],
                }
                for row in user_skill_rows
            ],
        )

    op.drop_constraint("user_skills_skill_id_fkey", "user_skills", type_="foreignkey")
    op.drop_constraint("uq_user_skills_user_skill", "user_skills", type_="unique")
    op.drop_constraint("user_skills_pkey", "user_skills", type_="primary")
    op.drop_constraint("skills_pkey", "skills", type_="primary")
    op.drop_column("user_skills", "id")
    op.drop_column("user_skills", "skill_id")
    op.drop_column("skills", "id")

    op.alter_column(
        "skills", "uuid_id", new_column_name="id", existing_type=sa.Uuid(), nullable=False
    )
    op.alter_column(
        "user_skills", "uuid_id", new_column_name="id", existing_type=sa.Uuid(), nullable=False
    )
    op.alter_column(
        "user_skills",
        "uuid_skill_id",
        new_column_name="skill_id",
        existing_type=sa.Uuid(),
        nullable=False,
    )

    op.create_primary_key("skills_pkey", "skills", ["id"])
    op.create_primary_key("user_skills_pkey", "user_skills", ["id"])
    op.create_foreign_key(
        "user_skills_skill_id_fkey",
        "user_skills",
        "skills",
        ["skill_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_unique_constraint("uq_user_skills_user_skill", "user_skills", ["user_id", "skill_id"])
    op.alter_column("skills", "id", comment=None)
    op.alter_column("user_skills", "id", comment=None)
