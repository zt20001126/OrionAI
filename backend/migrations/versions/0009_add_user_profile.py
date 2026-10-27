"""为用户增加昵称和头像地址。

Revision ID: 0009_add_user_profile
Revises: 0008_add_image_agent
Create Date: 2026-10-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_add_user_profile"
down_revision: str | None = "0008_add_image_agent"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEFAULT_USER_AVATAR_URL = "/avatar/default_avatar.png"


def upgrade() -> None:
    """新增用户昵称，并为现有和新用户设置项目默认头像。"""

    op.add_column(
        "users",
        sa.Column(
            "nickname",
            sa.String(length=20),
            nullable=True,
            comment="用户昵称；未设置时使用账号本地部分展示",
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "avatar_url",
            sa.String(length=2048),
            server_default=DEFAULT_USER_AVATAR_URL,
            nullable=False,
            comment="用户头像地址；注册默认项目头像，上传后保存 OSS 公开 URL",
        ),
    )


def downgrade() -> None:
    """删除用户昵称和头像地址字段。"""

    op.drop_column("users", "avatar_url")
    op.drop_column("users", "nickname")
