"""定义技能任务结果的关系模型。"""

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.infrastructure.database.base import Base
from app.infrastructure.database.snowflake import generate_snowflake_id


class TaskResult(Base):
    """保存技能执行结果及其用户、会话和技能归属。"""

    __tablename__ = "task_results"
    __table_args__ = (
        Index("ix_task_results_user_id_created_at", "user_id", "created_at"),
        Index("ix_task_results_conversation_id", "conversation_id"),
        Index("ix_task_results_skill_code", "skill_code"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer(), "sqlite"),
        primary_key=True,
        default=generate_snowflake_id,
        comment="任务结果唯一标识",
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer(), "sqlite"),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        comment="所属用户 ID",
    )
    conversation_id: Mapped[int | None] = mapped_column(
        BigInteger().with_variant(Integer(), "sqlite"),
        ForeignKey(
            "conversations.id",
            ondelete="SET NULL",
            name="fk_task_results_conversation_id_conversations",
        ),
        nullable=True,
        comment="关联会话 ID",
    )
    skill_code: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("skills.code", ondelete="RESTRICT", name="fk_task_results_skill_code_skills"),
        nullable=False,
        comment="对应技能代码",
    )
    result: Mapped[dict[str, Any]] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        comment="技能执行产生的 JSON 结果",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="创建时间",
    )
