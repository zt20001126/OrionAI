"""在 users 表保存 Gitee 身份，支持 OAuth-only 用户及邮箱账号绑定。"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0021_add_users_gitee_id"
down_revision: str | None = "0020_tourism_sentiment"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """为现有用户增加可空唯一 Gitee ID，不变更已有账号和用户 ID。"""
    op.add_column(
        "users",
        sa.Column("gitee_id", sa.String(length=255), nullable=True, comment="Gitee 用户唯一 ID"),
    )
    op.drop_constraint("ck_users_identity_credentials", "users", type_="check")
    op.create_check_constraint(
        "ck_users_identity_credentials",
        "users",
        "(is_guest AND account IS NULL AND password_hash IS NULL AND gitee_id IS NULL) "
        "OR (NOT is_guest AND ((account IS NOT NULL AND password_hash IS NOT NULL) "
        "OR (account IS NULL AND password_hash IS NULL AND gitee_id IS NOT NULL)))",
    )
    op.create_unique_constraint("uq_users_gitee_id", "users", ["gitee_id"])


def downgrade() -> None:
    """仅在没有 Gitee 用户或 OAuth-only 用户时移除字段。"""
    connection = op.get_bind()
    gitee_user_count = connection.scalar(
        sa.text("SELECT count(*) FROM users WHERE gitee_id IS NOT NULL")
    )
    if gitee_user_count:
        raise RuntimeError("无法回滚：仍有用户绑定 Gitee，需先迁移其认证方式。")
    oauth_only_count = connection.scalar(
        sa.text(
            "SELECT count(*) FROM users "
            "WHERE account IS NULL AND password_hash IS NULL AND is_guest IS FALSE"
        )
    )
    if oauth_only_count:
        raise RuntimeError("无法回滚：仍有 OAuth-only 用户，需先迁移其认证方式。")
    op.drop_constraint("uq_users_gitee_id", "users", type_="unique")
    op.drop_constraint("ck_users_identity_credentials", "users", type_="check")
    op.create_check_constraint(
        "ck_users_identity_credentials",
        "users",
        "(is_guest AND account IS NULL AND password_hash IS NULL) "
        "OR (NOT is_guest AND account IS NOT NULL AND password_hash IS NOT NULL)",
    )
    op.drop_column("users", "gitee_id")
