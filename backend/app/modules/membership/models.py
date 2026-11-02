"""定义会员套餐、购买订单和有效期限的 SQLAlchemy 持久化模型。"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    PrimaryKeyConstraint,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base
from app.infrastructure.database.snowflake import generate_snowflake_id
from app.modules.membership.constants import MembershipOrderStatus, MembershipOrderType


class MembershipPlan(Base):
    """会员套餐持久化模型，保存当前可售档位和固定有效天数。"""

    __tablename__ = "membership_plans"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_membership_plans"),
        CheckConstraint("price > 0", name="ck_membership_plans_price_positive"),
        CheckConstraint("duration_days > 0", name="ck_membership_plans_duration_positive"),
        UniqueConstraint("name", name="uq_membership_plans_name"),
        {"comment": "会员可售套餐配置；金额单位为人民币元"},
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer(), "sqlite"),
        primary_key=True,
        default=generate_snowflake_id,
        comment="套餐 Snowflake ID",
    )
    name: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="套餐展示名称及种子数据自然键"
    )
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, comment="套餐人民币售价")
    duration_days: Mapped[int] = mapped_column(Integer, nullable=False, comment="套餐固定有效天数")
    is_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true"), comment="是否接受新订单"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), comment="创建时间"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        comment="最近更新时间",
    )


class MembershipOrder(Base):
    """会员订单持久化模型，保存购买或赠送来源、金额和期限快照及支付会话关联。"""

    __tablename__ = "membership_orders"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_membership_orders"),
        CheckConstraint(
            f"(order_type = '{MembershipOrderType.PURCHASE.value}' AND amount > 0 "
            "AND grant_reason IS NULL) "
            f"OR (order_type = '{MembershipOrderType.MANUAL_GRANT.value}' "
            "AND amount = 0 AND grant_reason IS NOT NULL)",
            name="ck_membership_orders_amount_source",
        ),
        CheckConstraint("duration_days > 0", name="ck_membership_orders_duration_positive"),
        CheckConstraint(
            f"order_type IN ('{MembershipOrderType.PURCHASE.value}', "
            f"'{MembershipOrderType.MANUAL_GRANT.value}')",
            name="ck_membership_orders_type",
        ),
        CheckConstraint(
            f"order_type != '{MembershipOrderType.MANUAL_GRANT.value}' OR "
            f"(status = '{MembershipOrderStatus.PAID.value}' AND stripe_session_id IS NULL)",
            name="ck_membership_orders_manual_grant_state",
        ),
        CheckConstraint(
            "status IN ('pending', 'paid', 'failed', 'expired')",
            name="ck_membership_orders_status",
        ),
        UniqueConstraint("user_id", "request_id", name="uq_membership_orders_user_request"),
        UniqueConstraint("id", "user_id", name="uq_membership_orders_id_user"),
        UniqueConstraint("stripe_session_id", name="uq_membership_orders_stripe_session"),
        Index("ix_membership_orders_user_created", "user_id", "created_at"),
        {"comment": "会员购买与支付订单；金额和有效天数在下单时快照"},
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer(), "sqlite"),
        primary_key=True,
        default=generate_snowflake_id,
        comment="会员订单 Snowflake ID",
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer(), "sqlite"),
        ForeignKey("users.id", ondelete="RESTRICT", name="fk_membership_orders_user"),
        nullable=False,
        comment="下单用户 ID",
    )
    plan_id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer(), "sqlite"),
        ForeignKey("membership_plans.id", ondelete="RESTRICT", name="fk_membership_orders_plan"),
        nullable=False,
        comment="用户选择的会员套餐 ID",
    )
    amount: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, comment="下单时人民币金额快照"
    )
    order_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=MembershipOrderType.PURCHASE,
        server_default=text(f"'{MembershipOrderType.PURCHASE.value}'"),
        comment="订单来源类型：付费购买或管理员赠送",
    )
    grant_reason: Mapped[str | None] = mapped_column(
        String(500), nullable=True, comment="管理员赠送会员的原因；普通购买为空"
    )
    duration_days: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="下单时会员有效天数快照"
    )
    request_id: Mapped[str] = mapped_column(
        String(36), nullable=False, comment="客户端 UUID 幂等请求键"
    )
    stripe_session_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="Stripe Checkout Session 唯一关联 ID"
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="pending",
        server_default=text("'pending'"),
        comment="订单支付状态",
    )
    paid_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="服务端确认付款时间"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), comment="订单创建时间"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        comment="订单最近更新时间",
    )


class Membership(Base):
    """已购会员有效期限模型，每个成功订单最多生成一段期限。"""

    __tablename__ = "memberships"
    __table_args__ = (
        PrimaryKeyConstraint("order_id", name="pk_memberships"),
        ForeignKeyConstraint(
            ["order_id", "user_id"],
            ["membership_orders.id", "membership_orders.user_id"],
            ondelete="RESTRICT",
            name="fk_memberships_order_owner",
        ),
        ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="RESTRICT", name="fk_memberships_user"
        ),
        CheckConstraint("expires_at > starts_at", name="ck_memberships_expiry_after_start"),
        Index("ix_memberships_user_period", "user_id", "starts_at", "expires_at"),
        ExcludeConstraint(
            ("user_id", "="),
            (text("tstzrange(starts_at, expires_at, '[)')"), "&&"),
            using="gist",
            name="ex_memberships_user_period_no_overlap",
        ).ddl_if(dialect="postgresql"),
        {"comment": "已支付会员期限，采用左闭右开时间范围且同一用户期限不可重叠"},
    )

    order_id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer(), "sqlite"),
        primary_key=True,
        comment="对应的唯一会员订单 ID",
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer(), "sqlite"), nullable=False, comment="会员所属用户 ID"
    )
    starts_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment="会员期限生效时间（含）"
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment="会员期限失效时间（不含）"
    )
