"""创建会员套餐、会员订单与会员期限表，并写入首期固定套餐。

Revision ID: 0017_membership_billing
Revises: 0016_guest_users
Create Date: 2026-11-02
"""

import time
from collections.abc import Sequence
from decimal import Decimal

import sqlalchemy as sa
from alembic import op

revision: str = "0017_membership_billing"
down_revision: str | None = "0016_guest_users"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_EPOCH_MS = 1_704_067_200_000
_MIGRATION_WORKER_ID = 1023
_SEQUENCE_BITS = 12
_WORKER_ID_SHIFT = 12
_TIMESTAMP_SHIFT = 22
_MAX_SEQUENCE = (1 << _SEQUENCE_BITS) - 1
_MAX_TIMESTAMP_DELTA = (1 << 41) - 1
_SEED_PLANS = (
    ("月度会员", Decimal("9.90"), 30),
    ("季度会员", Decimal("99.90"), 90),
    ("年度会员", Decimal("999.90"), 365),
)


class _MigrationSnowflakeGenerator:
    """迁移内 Snowflake 算法快照，使用专用 worker 1023 且不依赖运行时代码。"""

    def __init__(self) -> None:
        self._last_timestamp_ms = -1
        self._sequence = 0

    def next_id(self) -> int:
        """按迁移专用 worker 生成正数 BIGINT ID。"""

        timestamp_ms = time.time_ns() // 1_000_000
        if timestamp_ms < self._last_timestamp_ms:
            timestamp_ms = self._wait_until_after(self._last_timestamp_ms)
        if timestamp_ms == self._last_timestamp_ms:
            self._sequence = (self._sequence + 1) & _MAX_SEQUENCE
            if self._sequence == 0:
                timestamp_ms = self._wait_until_after(self._last_timestamp_ms)
        else:
            self._sequence = 0

        self._last_timestamp_ms = timestamp_ms
        timestamp_delta = timestamp_ms - _EPOCH_MS
        if timestamp_delta < 0 or timestamp_delta > _MAX_TIMESTAMP_DELTA:
            raise RuntimeError("当前时间超出 Snowflake ID 支持范围。")
        return (
            (timestamp_delta << _TIMESTAMP_SHIFT)
            | (_MIGRATION_WORKER_ID << _WORKER_ID_SHIFT)
            | self._sequence
        )

    @staticmethod
    def _wait_until_after(timestamp_ms: int) -> int:
        """等待毫秒时钟前进，避免时钟回拨或序号耗尽导致重复 ID。"""

        current_timestamp_ms = time.time_ns() // 1_000_000
        while current_timestamp_ms <= timestamp_ms:
            time.sleep(0.001)
            current_timestamp_ms = time.time_ns() // 1_000_000
        return current_timestamp_ms


def upgrade() -> None:
    """创建会员三表、期限排斥约束和首期可售套餐。"""

    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    op.create_table(
        "membership_plans",
        sa.Column("id", sa.BigInteger(), nullable=False, comment="套餐 Snowflake ID"),
        sa.Column(
            "name", sa.String(length=100), nullable=False, comment="套餐展示名称及种子数据自然键"
        ),
        sa.Column(
            "price", sa.Numeric(precision=10, scale=2), nullable=False, comment="套餐人民币售价"
        ),
        sa.Column("duration_days", sa.Integer(), nullable=False, comment="套餐固定有效天数"),
        sa.Column(
            "is_enabled",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
            comment="是否接受新订单",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
            comment="创建时间",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
            comment="最近更新时间",
        ),
        sa.CheckConstraint("price > 0", name="ck_membership_plans_price_positive"),
        sa.CheckConstraint("duration_days > 0", name="ck_membership_plans_duration_positive"),
        sa.PrimaryKeyConstraint("id", name="pk_membership_plans"),
        sa.UniqueConstraint("name", name="uq_membership_plans_name"),
        comment="会员可售套餐配置；金额单位为人民币元",
    )
    op.create_table(
        "membership_orders",
        sa.Column("id", sa.BigInteger(), nullable=False, comment="会员订单 Snowflake ID"),
        sa.Column("user_id", sa.BigInteger(), nullable=False, comment="下单用户 ID"),
        sa.Column("plan_id", sa.BigInteger(), nullable=False, comment="用户选择的会员套餐 ID"),
        sa.Column(
            "amount",
            sa.Numeric(precision=10, scale=2),
            nullable=False,
            comment="下单时人民币金额快照",
        ),
        sa.Column("duration_days", sa.Integer(), nullable=False, comment="下单时会员有效天数快照"),
        sa.Column(
            "request_id", sa.String(length=36), nullable=False, comment="客户端 UUID 幂等请求键"
        ),
        sa.Column(
            "stripe_session_id",
            sa.String(length=255),
            nullable=True,
            comment="Stripe Checkout Session 唯一关联 ID",
        ),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default=sa.text("'pending'"),
            nullable=False,
            comment="订单支付状态",
        ),
        sa.Column(
            "paid_at", sa.DateTime(timezone=True), nullable=True, comment="服务端确认付款时间"
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
            comment="订单创建时间",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
            comment="订单最近更新时间",
        ),
        sa.CheckConstraint("amount > 0", name="ck_membership_orders_amount_positive"),
        sa.CheckConstraint("duration_days > 0", name="ck_membership_orders_duration_positive"),
        sa.CheckConstraint(
            "status IN ('pending', 'paid', 'failed', 'expired')",
            name="ck_membership_orders_status",
        ),
        sa.ForeignKeyConstraint(
            ["plan_id"],
            ["membership_plans.id"],
            ondelete="RESTRICT",
            name="fk_membership_orders_plan",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="RESTRICT", name="fk_membership_orders_user"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_membership_orders"),
        sa.UniqueConstraint("id", "user_id", name="uq_membership_orders_id_user"),
        sa.UniqueConstraint("stripe_session_id", name="uq_membership_orders_stripe_session"),
        sa.UniqueConstraint("user_id", "request_id", name="uq_membership_orders_user_request"),
        comment="会员购买与支付订单；金额和有效天数在下单时快照",
    )
    op.create_index(
        "ix_membership_orders_user_created",
        "membership_orders",
        ["user_id", "created_at"],
    )
    op.create_table(
        "memberships",
        sa.Column("order_id", sa.BigInteger(), nullable=False, comment="对应的唯一会员订单 ID"),
        sa.Column("user_id", sa.BigInteger(), nullable=False, comment="会员所属用户 ID"),
        sa.Column(
            "starts_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="会员期限生效时间（含）",
        ),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="会员期限失效时间（不含）",
        ),
        sa.CheckConstraint("expires_at > starts_at", name="ck_memberships_expiry_after_start"),
        sa.ForeignKeyConstraint(
            ["order_id", "user_id"],
            ["membership_orders.id", "membership_orders.user_id"],
            ondelete="RESTRICT",
            name="fk_memberships_order_owner",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="RESTRICT", name="fk_memberships_user"
        ),
        sa.PrimaryKeyConstraint("order_id", name="pk_memberships"),
        comment="已支付会员期限，采用左闭右开时间范围且同一用户期限不可重叠",
    )
    op.create_index(
        "ix_memberships_user_period",
        "memberships",
        ["user_id", "starts_at", "expires_at"],
    )
    op.execute(
        "ALTER TABLE memberships ADD CONSTRAINT ex_memberships_user_period_no_overlap "
        "EXCLUDE USING gist (user_id WITH =, "
        "tstzrange(starts_at, expires_at, '[)') WITH &&)"
    )

    generator = _MigrationSnowflakeGenerator()
    seed_rows = [
        {"id": generator.next_id(), "name": name, "price": price, "duration_days": duration_days}
        for name, price, duration_days in _SEED_PLANS
    ]
    connection = op.get_bind()
    connection.execute(
        sa.text(
            "INSERT INTO membership_plans (id, name, price, duration_days, is_enabled) "
            "VALUES (:id, :name, :price, :duration_days, true) "
            "ON CONFLICT (name) DO NOTHING"
        ),
        seed_rows,
    )


def downgrade() -> None:
    """按依赖顺序删除会员业务表，但保留可能被其他模块使用的扩展。"""

    op.drop_index("ix_memberships_user_period", table_name="memberships")
    op.drop_table("memberships")
    op.drop_index("ix_membership_orders_user_created", table_name="membership_orders")
    op.drop_table("membership_orders")
    op.drop_table("membership_plans")
