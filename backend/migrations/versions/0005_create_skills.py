"""创建技能市场与用户技能关联表，并注册通用对话助手。

Revision ID: 0005_create_skills
Revises: 0004_snowflake_primary_ids
Create Date: 2026-10-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_create_skills"
down_revision: str | None = "0004_snowflake_primary_ids"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "skills",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("type", sa.String(length=20), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default=sa.text("'published'"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("type IN ('agent', 'tool')", name="ck_skills_type"),
        sa.CheckConstraint("status IN ('published', 'disabled')", name="ck_skills_status"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index(
        "ix_skills_status_type_created_at",
        "skills",
        ["status", "type", "created_at"],
    )
    op.create_table(
        "user_skills",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("skill_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["skill_id"], ["skills.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "skill_id", name="uq_user_skills_user_skill"),
    )
    op.create_index(
        "ix_user_skills_user_created_at",
        "user_skills",
        ["user_id", "created_at"],
    )
    op.execute(
        sa.text(
            "INSERT INTO skills (id, code, name, description, type, status) "
            "VALUES ('2a45c2d2-2bf7-4a15-a830-75c09154eef6', 'general_chat', "
            "'通用对话助手', '支持日常问答和多轮对话', 'agent', 'published') "
            "ON CONFLICT (code) DO NOTHING"
        )
    )


def downgrade() -> None:
    op.drop_index("ix_user_skills_user_created_at", table_name="user_skills")
    op.drop_table("user_skills")
    op.drop_index("ix_skills_status_type_created_at", table_name="skills")
    op.drop_table("skills")
