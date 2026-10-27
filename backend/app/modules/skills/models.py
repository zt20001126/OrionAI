"""定义平台技能及用户技能关联的持久化模型。"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base
from app.infrastructure.database.snowflake import generate_snowflake_id


class Skill(Base):
    """平台级技能定义，不保存智能体或工具的可执行实现。"""

    __tablename__ = "skills"
    __table_args__ = (
        CheckConstraint("type IN ('agent', 'tool')", name="ck_skills_type"),
        CheckConstraint("status IN ('published', 'disabled')", name="ck_skills_status"),
        Index("ix_skills_status_type_created_at", "status", "type", "created_at"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer(), "sqlite"),
        primary_key=True,
        default=generate_snowflake_id,
        comment="技能 Snowflake ID",
    )
    code: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="published", server_default="published"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class UserSkill(Base):
    """保存用户技能关联及关联时的技能名称快照。"""

    __tablename__ = "user_skills"
    __table_args__ = (
        UniqueConstraint("user_id", "skill_id", name="uq_user_skills_user_skill"),
        Index("ix_user_skills_user_created_at", "user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer(), "sqlite"),
        primary_key=True,
        default=generate_snowflake_id,
        comment="用户技能关联 Snowflake ID",
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer(), "sqlite"),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    skill_id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer(), "sqlite"),
        ForeignKey("skills.id", ondelete="CASCADE"),
        nullable=False,
    )
    skill_name: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="用户关联技能名称快照"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
