"""Add temporary guest identities to the existing users table."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016_guest_users"
down_revision: str | None = "0015_create_memory_images"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """保留既有邮箱用户，并允许 users 表保存无邮箱的访客主体。"""

    op.add_column(
        "users",
        sa.Column(
            "is_guest",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
            comment="是否为临时访客身份",
        ),
    )
    op.alter_column(
        "users",
        "account",
        existing_type=sa.String(length=254),
        nullable=True,
    )
    op.alter_column(
        "users",
        "password_hash",
        existing_type=sa.String(length=256),
        nullable=True,
    )
    op.create_check_constraint(
        "ck_users_identity_credentials",
        "users",
        "(is_guest AND account IS NULL AND password_hash IS NULL) "
        "OR (NOT is_guest AND account IS NOT NULL AND password_hash IS NOT NULL)",
    )


def downgrade() -> None:
    """仅在没有访客数据时回滚，避免级联删除访客业务数据。"""

    connection = op.get_bind()
    guest_count = connection.scalar(sa.text("SELECT count(*) FROM users WHERE is_guest IS TRUE"))
    if guest_count:
        raise RuntimeError("无法回滚：users 表仍有访客记录及其业务数据。")

    op.drop_constraint("ck_users_identity_credentials", "users", type_="check")
    op.alter_column(
        "users",
        "password_hash",
        existing_type=sa.String(length=256),
        nullable=False,
    )
    op.alter_column(
        "users",
        "account",
        existing_type=sa.String(length=254),
        nullable=False,
    )
    op.drop_column("users", "is_guest")
