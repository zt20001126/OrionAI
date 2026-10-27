"""定义用户简历的关系持久化模型。"""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.infrastructure.database.base import Base
from app.infrastructure.database.snowflake import generate_snowflake_id


class Resume(Base):
    """每个用户最多保存一份结构化 JSON 简历。"""

    __tablename__ = "resumes"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_resumes_user_id"),
        CheckConstraint(
            "jsonb_typeof(content) = 'object'", name="ck_resumes_content_object"
        ).ddl_if(dialect="postgresql"),
        CheckConstraint(
            "jsonb_typeof(style_config) = 'object'", name="ck_resumes_style_config_object"
        ).ddl_if(dialect="postgresql"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer(), "sqlite"),
        primary_key=True,
        default=generate_snowflake_id,
        comment="简历 Snowflake ID",
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer(), "sqlite"),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        comment="简历所属用户",
    )
    content: Mapped[dict[str, Any]] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=False
    )
    style_config: Mapped[dict[str, Any]] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
