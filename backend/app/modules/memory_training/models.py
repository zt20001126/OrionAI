"""定义记忆训练图片素材的 PostgreSQL 持久化模型。"""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Index, Integer, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base
from app.infrastructure.database.snowflake import generate_snowflake_id


class MemoryImage(Base):
    """图片素材目录，仅保存公开 OSS 链接和启用状态。"""

    __tablename__ = "memory_images"
    __table_args__ = (
        Index(
            "ix_memory_images_enabled_id",
            "id",
            postgresql_where=text("enabled IS TRUE"),
            sqlite_where=text("enabled IS TRUE"),
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer(), "sqlite"),
        primary_key=True,
        autoincrement=False,
        default=generate_snowflake_id,
        comment="图片素材 Snowflake ID",
    )
    image_url: Mapped[str] = mapped_column(
        String(2048), nullable=False, unique=True, comment="图片公开访问链接"
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true"), comment="是否启用"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, comment="素材登记时间"
    )
