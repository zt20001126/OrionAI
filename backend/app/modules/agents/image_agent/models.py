"""图片助手任务结果及私有对象元数据。"""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.infrastructure.database.base import Base
from app.infrastructure.database.snowflake import generate_snowflake_id


class ImageTaskResult(Base):
    """不在数据库保存图片字节，只保存状态、输入和 OSS 结果元数据。"""

    __tablename__ = "task_results"
    __table_args__ = (
        CheckConstraint(
            "generation_status IN ('running', 'succeeded', 'failed')",
            name="ck_task_results_generation_status",
        ),
        Index("ix_task_results_user_id_created_at", "user_id", "created_at"),
        Index("ix_task_results_conversation_id", "conversation_id"),
    )

    task_result_id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer(), "sqlite"),
        primary_key=True,
        default=generate_snowflake_id,
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer(), "sqlite"),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    conversation_id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer(), "sqlite"),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    message_id: Mapped[int | None] = mapped_column(
        BigInteger().with_variant(Integer(), "sqlite"),
        ForeignKey("messages.id", ondelete="SET NULL"),
        nullable=True,
    )
    agent_code: Mapped[str] = mapped_column(String(100), nullable=False, default="image_agent")
    generation_status: Mapped[str] = mapped_column(String(20), nullable=False)
    input_data: Mapped[dict[str, Any]] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=False
    )
    result_data: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
