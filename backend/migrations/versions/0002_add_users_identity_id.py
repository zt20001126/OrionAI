"""为用户表增加 BIGINT Identity 主键并保留账号唯一性。

Revision ID: 0002_add_users_identity_id
Revises: 0001_create_users
Create Date: 2026-10-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_add_users_identity_id"
down_revision: str | None = "0001_create_users"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
    )
    op.create_unique_constraint("uq_users_account", "users", ["account"])
    op.drop_constraint("users_pkey", "users", type_="primary")
    op.create_primary_key("users_pkey", "users", ["id"])


def downgrade() -> None:
    op.drop_constraint("users_pkey", "users", type_="primary")
    op.create_primary_key("users_pkey", "users", ["account"])
    op.drop_constraint("uq_users_account", "users", type_="unique")
    op.drop_column("users", "id")
