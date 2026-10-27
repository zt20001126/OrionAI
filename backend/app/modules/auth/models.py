from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base
from app.infrastructure.database.snowflake import generate_snowflake_id

DEFAULT_USER_AVATAR_URL = "/avatar/default_avatar.png"


class User(Base):
    """认证模块的用户持久化模型，用户 ID 由 Snowflake 生成。"""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer(), "sqlite"),
        primary_key=True,
        default=generate_snowflake_id,
        comment="用户 Snowflake ID",
    )
    account: Mapped[str] = mapped_column(String(254), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    nickname: Mapped[str | None] = mapped_column(
        String(20), nullable=True, comment="用户昵称；未设置时使用账号本地部分展示"
    )
    avatar_key: Mapped[str | None] = mapped_column(
        String(1024), nullable=True, comment="用户头像在 OSS 中的对象键"
    )
    avatar_url: Mapped[str | None] = mapped_column(
        String(2048),
        nullable=True,
        comment="兼容既有头像地址；新头像仅保存 avatar_key",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
