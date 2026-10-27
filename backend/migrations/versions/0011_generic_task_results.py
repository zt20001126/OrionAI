"""将图片专用任务记录调整为技能通用结果表。"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011_generic_task_results"
down_revision: str | None = "0010_add_user_avatar_key"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """保留既有图片任务数据，并将结果字段统一存入 JSONB。"""
    op.add_column(
        "task_results",
        sa.Column(
            "result",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="技能执行产生的 JSON 结果",
        ),
    )
    op.execute(
        sa.text(
            "UPDATE task_results SET result = jsonb_build_object("
            "'generation_status', generation_status, "
            "'input_data', input_data, 'result_data', result_data)"
        )
    )

    op.alter_column(
        "task_results",
        "task_result_id",
        new_column_name="id",
        existing_type=sa.BigInteger(),
        existing_nullable=False,
        comment="任务结果唯一标识",
    )
    op.alter_column(
        "task_results",
        "agent_code",
        new_column_name="skill_code",
        existing_type=sa.String(length=100),
        existing_nullable=False,
        server_default=None,
        comment="对应技能代码",
    )
    op.create_foreign_key(
        "fk_task_results_skill_code_skills",
        "task_results",
        "skills",
        ["skill_code"],
        ["code"],
        ondelete="RESTRICT",
    )
    op.create_index("ix_task_results_skill_code", "task_results", ["skill_code"])
    op.alter_column(
        "task_results",
        "user_id",
        existing_type=sa.BigInteger(),
        existing_nullable=False,
        comment="所属用户 ID",
    )
    op.alter_column(
        "task_results",
        "created_at",
        existing_type=sa.DateTime(timezone=True),
        existing_nullable=False,
        comment="创建时间",
    )

    op.drop_constraint("task_results_conversation_id_fkey", "task_results", type_="foreignkey")
    op.alter_column(
        "task_results",
        "conversation_id",
        existing_type=sa.BigInteger(),
        existing_nullable=False,
        nullable=True,
        comment="关联会话 ID",
    )
    op.create_foreign_key(
        "fk_task_results_conversation_id_conversations",
        "task_results",
        "conversations",
        ["conversation_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.drop_constraint("task_results_message_id_fkey", "task_results", type_="foreignkey")
    op.drop_constraint("ck_task_results_generation_status", "task_results", type_="check")
    op.drop_column("task_results", "message_id")
    op.drop_column("task_results", "generation_status")
    op.drop_column("task_results", "input_data")
    op.drop_column("task_results", "result_data")
    op.drop_column("task_results", "updated_at")
    op.alter_column(
        "task_results",
        "result",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        nullable=False,
    )


def downgrade() -> None:
    """恢复图片专用列；存在通用技能结果或空会话引用时拒绝降级。"""
    connection = op.get_bind()
    has_incompatible_results = connection.scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM task_results "
            "WHERE skill_code <> 'image_agent' OR conversation_id IS NULL)"
        )
    )
    if has_incompatible_results:
        raise RuntimeError("task_results 中存在非图片技能结果或无会话结果，无法安全降级到旧结构。")

    op.drop_index("ix_task_results_skill_code", table_name="task_results")
    op.drop_constraint("fk_task_results_skill_code_skills", "task_results", type_="foreignkey")
    op.drop_constraint(
        "fk_task_results_conversation_id_conversations",
        "task_results",
        type_="foreignkey",
    )
    op.alter_column(
        "task_results",
        "conversation_id",
        existing_type=sa.BigInteger(),
        existing_nullable=True,
        nullable=False,
        comment=None,
    )
    op.create_foreign_key(
        "task_results_conversation_id_fkey",
        "task_results",
        "conversations",
        ["conversation_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.add_column(
        "task_results",
        sa.Column("generation_status", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "task_results",
        sa.Column("input_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "task_results",
        sa.Column("result_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column("task_results", sa.Column("message_id", sa.BigInteger(), nullable=True))
    op.execute(
        sa.text(
            "UPDATE task_results SET "
            "generation_status = COALESCE(result ->> 'generation_status', 'succeeded'), "
            "input_data = COALESCE(result -> 'input_data', '{}'::jsonb), "
            "result_data = result -> 'result_data'"
        )
    )
    op.alter_column(
        "task_results", "generation_status", existing_type=sa.String(length=20), nullable=False
    )
    op.alter_column("task_results", "input_data", existing_type=postgresql.JSONB(), nullable=False)
    op.drop_column("task_results", "result")
    op.alter_column(
        "task_results",
        "skill_code",
        new_column_name="agent_code",
        existing_type=sa.String(length=100),
        existing_nullable=False,
        server_default="image_agent",
        comment=None,
    )
    op.alter_column(
        "task_results",
        "user_id",
        existing_type=sa.BigInteger(),
        existing_nullable=False,
        comment=None,
    )
    op.alter_column(
        "task_results",
        "created_at",
        existing_type=sa.DateTime(timezone=True),
        existing_nullable=False,
        comment=None,
    )
    op.alter_column(
        "task_results",
        "id",
        new_column_name="task_result_id",
        existing_type=sa.BigInteger(),
        existing_nullable=False,
        comment=None,
    )
    op.add_column(
        "task_results",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_foreign_key(
        "task_results_message_id_fkey",
        "task_results",
        "messages",
        ["message_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_check_constraint(
        "ck_task_results_generation_status",
        "task_results",
        "generation_status IN ('running', 'succeeded', 'failed')",
    )
