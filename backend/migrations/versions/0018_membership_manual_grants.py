"""支持以零金额订单记录管理员手动赠送的会员期限。

Revision ID: 0018_membership_manual_grants
Revises: 0017_membership_billing
Create Date: 2026-11-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018_membership_manual_grants"
down_revision: str | None = "0017_membership_billing"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """为会员订单增加赠送来源和原因，并限制赠送订单必须零金额且已发放。"""

    op.add_column(
        "membership_orders",
        sa.Column(
            "order_type",
            sa.String(length=20),
            server_default=sa.text("'purchase'"),
            nullable=False,
            comment="订单来源类型：付费购买或管理员赠送",
        ),
    )
    op.add_column(
        "membership_orders",
        sa.Column(
            "grant_reason",
            sa.String(length=500),
            nullable=True,
            comment="管理员赠送会员的原因；普通购买为空",
        ),
    )
    op.drop_constraint(
        "ck_membership_orders_amount_positive",
        "membership_orders",
        type_="check",
    )
    op.create_check_constraint(
        "ck_membership_orders_amount_source",
        "membership_orders",
        "(order_type = 'purchase' AND amount > 0 AND grant_reason IS NULL) "
        "OR (order_type = 'manual_grant' AND amount = 0 AND grant_reason IS NOT NULL)",
    )
    op.create_check_constraint(
        "ck_membership_orders_type",
        "membership_orders",
        "order_type IN ('purchase', 'manual_grant')",
    )
    op.create_check_constraint(
        "ck_membership_orders_manual_grant_state",
        "membership_orders",
        "order_type != 'manual_grant' OR (status = 'paid' AND stripe_session_id IS NULL)",
    )


def downgrade() -> None:
    """仅在不存在赠送订单时回退，避免静默丢弃后台发放记录。"""

    connection = op.get_bind()
    manual_grant_count = connection.scalar(
        sa.text("SELECT count(*) FROM membership_orders WHERE order_type = 'manual_grant'")
    )
    if manual_grant_count:
        raise RuntimeError("存在管理员赠送订单，需先人工处理后再回退会员赠送迁移。")

    op.drop_constraint(
        "ck_membership_orders_manual_grant_state",
        "membership_orders",
        type_="check",
    )
    op.drop_constraint("ck_membership_orders_type", "membership_orders", type_="check")
    op.drop_constraint(
        "ck_membership_orders_amount_source",
        "membership_orders",
        type_="check",
    )
    op.create_check_constraint(
        "ck_membership_orders_amount_positive",
        "membership_orders",
        "amount > 0",
    )
    op.drop_column("membership_orders", "grant_reason")
    op.drop_column("membership_orders", "order_type")
