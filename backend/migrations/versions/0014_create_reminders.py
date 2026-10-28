"""Create reminder rules and reminder execution history.

Revision ID: 0014_create_reminders
Revises: 0013_rename_general_chat
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014_create_reminders"
down_revision: str | None = "0013_rename_general_chat"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    """仅创建提醒规则表与每次提醒执行历史表。"""

    op.create_table(
        "reminders",
        sa.Column(
            "id",
            sa.BigInteger(),
            autoincrement=False,
            nullable=False,
            comment="提醒 Snowflake ID",
        ),
        sa.Column("user_id", sa.BigInteger(), nullable=False, comment="提醒所属用户 ID"),
        sa.Column("title", sa.String(length=120), nullable=False, comment="提醒标题"),
        sa.Column("content", sa.Text(), nullable=False, comment="提醒正文"),
        sa.Column(
            "repeat_type",
            sa.String(length=16),
            nullable=False,
            comment="重复类型 once/daily/weekly/monthly",
        ),
        sa.Column(
            "repeat_config",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
            comment="周期规则 JSON 对象",
        ),
        sa.Column("timezone", sa.String(length=64), nullable=False, comment="IANA 时区名称"),
        sa.Column(
            "next_run_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="下一次计划时间，存储为 UTC",
        ),
        sa.Column("end_date", sa.Date(), nullable=True, comment="包含的最后一个本地日历日期"),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default="active",
            nullable=False,
            comment="提醒生命周期状态",
        ),
        sa.Column(
            "version",
            sa.Integer(),
            server_default="1",
            nullable=False,
            comment="乐观并发版本号",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
            comment="提醒创建时间",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
            comment="提醒最后更新时间",
        ),
        sa.CheckConstraint(
            "repeat_type IN ('once', 'daily', 'weekly', 'monthly')",
            name="ck_reminders_repeat_type",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'paused', 'cancelled', 'completed')",
            name="ck_reminders_status",
        ),
        sa.CheckConstraint(
            "length(trim(title)) BETWEEN 1 AND 120",
            name="ck_reminders_title_length",
        ),
        sa.CheckConstraint(
            "length(trim(content)) BETWEEN 1 AND 5000",
            name="ck_reminders_content_length",
        ),
        sa.CheckConstraint(
            "end_date IS NULL OR repeat_type <> 'once'",
            name="ck_reminders_end_date_repeat",
        ),
        sa.CheckConstraint("version > 0", name="ck_reminders_version_positive"),
        sa.CheckConstraint(
            "jsonb_typeof(repeat_config) = 'object'",
            name="ck_reminders_repeat_config_object",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_reminders_due",
        "reminders",
        ["next_run_at", "id"],
        unique=False,
        postgresql_where=sa.text("status = 'active' AND next_run_at IS NOT NULL"),
    )
    op.create_index(
        "ix_reminders_user_created",
        "reminders",
        ["user_id", sa.text("created_at DESC"), sa.text("id DESC")],
        unique=False,
    )

    op.create_table(
        "reminder_executions",
        sa.Column(
            "id",
            sa.BigInteger(),
            autoincrement=False,
            nullable=False,
            comment="提醒执行 Snowflake ID",
        ),
        sa.Column("reminder_id", sa.BigInteger(), nullable=False, comment="所属提醒 ID"),
        sa.Column(
            "scheduled_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="本次计划时间，存储为 UTC",
        ),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default="pending",
            nullable=False,
            comment="执行状态",
        ),
        sa.Column(
            "retry_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
            comment="已发生的失败重试次数",
        ),
        sa.Column(
            "next_retry_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="下次重试时间，存储为 UTC",
        ),
        sa.Column("recipient_email", sa.String(length=254), nullable=True, comment="账号邮箱快照"),
        sa.Column("error_message", sa.Text(), nullable=True, comment="最近失败的安全摘要"),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="最近一次尝试开始时间",
        ),
        sa.Column(
            "finished_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="执行进入终态的时间",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
            comment="执行记录创建时间",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'sending', 'retry_wait', 'accepted', 'failed', 'cancelled')",
            name="ck_reminder_executions_status",
        ),
        sa.CheckConstraint("retry_count >= 0", name="ck_reminder_executions_retry_count"),
        sa.CheckConstraint("retry_count <= 4", name="ck_reminder_executions_retry_count_max"),
        sa.CheckConstraint(
            "(status = 'retry_wait') = (next_retry_at IS NOT NULL)",
            name="ck_reminder_executions_retry_schedule",
        ),
        sa.ForeignKeyConstraint(["reminder_id"], ["reminders.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("reminder_id", "scheduled_at", name="uq_reminder_executions_schedule"),
    )
    op.create_index(
        "ix_reminder_executions_history",
        "reminder_executions",
        ["reminder_id", sa.text("scheduled_at DESC"), sa.text("id DESC")],
        unique=False,
    )
    op.create_index(
        "ix_reminder_executions_retry",
        "reminder_executions",
        ["next_retry_at", "id"],
        unique=False,
        postgresql_where=sa.text("status = 'retry_wait'"),
    )
    op.create_index(
        "ix_reminder_executions_stale",
        "reminder_executions",
        ["started_at", "id"],
        unique=False,
        postgresql_where=sa.text("status = 'sending'"),
    )


def downgrade() -> None:
    """按外键依赖逆序删除本迁移创建的两张提醒表。"""

    op.drop_index("ix_reminder_executions_stale", table_name="reminder_executions")
    op.drop_index("ix_reminder_executions_retry", table_name="reminder_executions")
    op.drop_index("ix_reminder_executions_history", table_name="reminder_executions")
    op.drop_table("reminder_executions")
    op.drop_index("ix_reminders_user_created", table_name="reminders")
    op.drop_index("ix_reminders_due", table_name="reminders")
    op.drop_table("reminders")
