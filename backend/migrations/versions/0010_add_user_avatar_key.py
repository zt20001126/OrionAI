"""为用户资料保存 OSS 头像对象键。"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_add_user_avatar_key"
down_revision: str | None = "0009_add_user_profile"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEFAULT_USER_AVATAR_URL = "/avatar/default_avatar.png"


def upgrade() -> None:
    """保留现有用户及自定义头像，并停止将默认图片地址写入用户记录。"""

    op.add_column(
        "users",
        sa.Column(
            "avatar_key",
            sa.String(length=1024),
            nullable=True,
            comment="用户头像在 OSS 中的对象键",
        ),
    )
    op.alter_column(
        "users",
        "avatar_url",
        existing_type=sa.String(length=2048),
        nullable=True,
        server_default=None,
    )
    op.execute(
        sa.text("UPDATE users SET avatar_url = NULL WHERE avatar_url = :default_url").bindparams(
            default_url=DEFAULT_USER_AVATAR_URL
        )
    )


def downgrade() -> None:
    """恢复旧头像列约束，保留用户及其头像信息。"""

    op.execute(
        sa.text("UPDATE users SET avatar_url = :default_url WHERE avatar_url IS NULL").bindparams(
            default_url=DEFAULT_USER_AVATAR_URL
        )
    )
    op.alter_column(
        "users",
        "avatar_url",
        existing_type=sa.String(length=2048),
        nullable=False,
        server_default=DEFAULT_USER_AVATAR_URL,
    )
    op.drop_column("users", "avatar_key")
