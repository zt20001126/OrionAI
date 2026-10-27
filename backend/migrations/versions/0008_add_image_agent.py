"""绑定会话技能并持久化图片助手任务结果。

Revision ID: 0008_add_image_agent
Revises: 0007_add_user_skill_name
Create Date: 2026-10-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008_add_image_agent"
down_revision: str | None = "0007_add_user_skill_name"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """旧会话绑定通用助手，并新增私有图片任务结果表。"""
    with op.batch_alter_table("conversations") as batch:
        batch.add_column(
            sa.Column(
                "skill_code", sa.String(length=100), nullable=True, server_default="general_chat"
            )
        )
    op.execute(
        sa.text("UPDATE conversations SET skill_code = 'general_chat' WHERE skill_code IS NULL")
    )
    with op.batch_alter_table("conversations") as batch:
        batch.alter_column(
            "skill_code",
            existing_type=sa.String(length=100),
            nullable=False,
            server_default="general_chat",
        )
        batch.create_foreign_key(
            "fk_conversations_skill_code_skills",
            "skills",
            ["skill_code"],
            ["code"],
            ondelete="RESTRICT",
        )

    op.create_table(
        "task_results",
        sa.Column("task_result_id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "conversation_id",
            sa.BigInteger(),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "message_id",
            sa.BigInteger(),
            sa.ForeignKey("messages.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "agent_code", sa.String(length=100), nullable=False, server_default="image_agent"
        ),
        sa.Column("generation_status", sa.String(length=20), nullable=False),
        sa.Column(
            "input_data",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "result_data",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "generation_status IN ('running', 'succeeded', 'failed')",
            name="ck_task_results_generation_status",
        ),
    )
    op.create_index("ix_task_results_user_id_created_at", "task_results", ["user_id", "created_at"])
    op.create_index("ix_task_results_conversation_id", "task_results", ["conversation_id"])


def downgrade() -> None:
    """移除图片任务结果并取消会话技能绑定。"""
    op.drop_index("ix_task_results_conversation_id", table_name="task_results")
    op.drop_index("ix_task_results_user_id_created_at", table_name="task_results")
    op.drop_table("task_results")
    with op.batch_alter_table("conversations") as batch:
        batch.drop_constraint("fk_conversations_skill_code_skills", type_="foreignkey")
        batch.drop_column("skill_code")
