"""定义提醒规则和每次提醒执行的数据库持久化模型。"""

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.infrastructure.database.base import Base
from app.infrastructure.database.snowflake import generate_snowflake_id
from app.modules.reminders.constants import (
    EXECUTION_PENDING,
    MAX_RETRY_COUNT,
    REMINDER_ACTIVE,
)


class Reminder(Base):
    """提醒规则持久化模型，保存归属用户、本地规则及当前执行计划。"""

    __tablename__ = "reminders"
    __table_args__ = (
        CheckConstraint(
            "repeat_type IN ('once', 'daily', 'weekly', 'monthly')",
            name="ck_reminders_repeat_type",
        ),
        CheckConstraint(
            "status IN ('active', 'paused', 'cancelled', 'completed')",
            name="ck_reminders_status",
        ),
        CheckConstraint(
            "length(trim(title)) BETWEEN 1 AND 120",
            name="ck_reminders_title_length",
        ),
        CheckConstraint(
            "length(trim(content)) BETWEEN 1 AND 5000",
            name="ck_reminders_content_length",
        ),
        CheckConstraint(
            "end_date IS NULL OR repeat_type <> 'once'",
            name="ck_reminders_end_date_repeat",
        ),
        CheckConstraint("version > 0", name="ck_reminders_version_positive"),
        CheckConstraint(
            "jsonb_typeof(repeat_config) = 'object'",
            name="ck_reminders_repeat_config_object",
        ).ddl_if(dialect="postgresql"),
        Index(
            "ix_reminders_due",
            "next_run_at",
            "id",
            postgresql_where=text("status = 'active' AND next_run_at IS NOT NULL"),
            sqlite_where=text("status = 'active' AND next_run_at IS NOT NULL"),
        ),
        Index(
            "ix_reminders_user_created",
            "user_id",
            text("created_at DESC"),
            text("id DESC"),
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer(), "sqlite"),
        primary_key=True,
        autoincrement=False,
        default=generate_snowflake_id,
        comment="提醒 Snowflake ID",
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer(), "sqlite"),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        comment="提醒所属用户 ID",
    )
    title: Mapped[str] = mapped_column(String(120), nullable=False, comment="提醒标题")
    content: Mapped[str] = mapped_column(Text, nullable=False, comment="提醒正文")
    repeat_type: Mapped[str] = mapped_column(
        String(16), nullable=False, comment="重复类型 once/daily/weekly/monthly"
    )
    repeat_config: Mapped[dict[str, Any]] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=dict,
        server_default=text("'{}'"),
        comment="周期规则 JSON 对象",
    )
    timezone: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="提醒使用的 IANA 时区名称"
    )
    next_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="下一次计划时间，存储为 UTC"
    )
    end_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="周期提醒包含的最后一个本地日期"
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=REMINDER_ACTIVE,
        server_default=REMINDER_ACTIVE,
        comment="提醒状态",
    )
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1", comment="乐观并发版本号"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, comment="创建时间"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        comment="最后更新时间",
    )


class ReminderExecution(Base):
    """提醒执行持久化模型，记录计划时刻、SMTP 结果与有限重试状态。"""

    __tablename__ = "reminder_executions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'sending', 'retry_wait', 'accepted', 'failed', 'cancelled')",
            name="ck_reminder_executions_status",
        ),
        CheckConstraint("retry_count >= 0", name="ck_reminder_executions_retry_count"),
        CheckConstraint(
            f"retry_count <= {MAX_RETRY_COUNT}",
            name="ck_reminder_executions_retry_count_max",
        ),
        CheckConstraint(
            "(status = 'retry_wait') = (next_retry_at IS NOT NULL)",
            name="ck_reminder_executions_retry_schedule",
        ),
        UniqueConstraint("reminder_id", "scheduled_at", name="uq_reminder_executions_schedule"),
        Index(
            "ix_reminder_executions_history",
            "reminder_id",
            text("scheduled_at DESC"),
            text("id DESC"),
        ),
        Index(
            "ix_reminder_executions_retry",
            "next_retry_at",
            "id",
            postgresql_where=text("status = 'retry_wait'"),
            sqlite_where=text("status = 'retry_wait'"),
        ),
        Index(
            "ix_reminder_executions_stale",
            "started_at",
            "id",
            postgresql_where=text("status = 'sending'"),
            sqlite_where=text("status = 'sending'"),
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer(), "sqlite"),
        primary_key=True,
        autoincrement=False,
        default=generate_snowflake_id,
        comment="提醒执行 Snowflake ID",
    )
    reminder_id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer(), "sqlite"),
        ForeignKey("reminders.id", ondelete="CASCADE"),
        nullable=False,
        comment="所属提醒 ID",
    )
    scheduled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment="本次计划时间，存储为 UTC"
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=EXECUTION_PENDING,
        server_default=EXECUTION_PENDING,
        comment="执行状态",
    )
    retry_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0", comment="已发生的失败重试次数"
    )
    next_retry_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="下次重试时间，存储为 UTC"
    )
    recipient_email: Mapped[str | None] = mapped_column(
        String(254), nullable=True, comment="认领时账号邮箱快照"
    )
    error_message: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="最近一次失败的安全摘要"
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="最近一次尝试开始时间"
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="执行进入终态的时间"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, comment="记录创建时间"
    )
