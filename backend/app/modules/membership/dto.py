"""定义会员模块跨应用用例边界使用的内部数据对象。"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum


class PaymentEventOutcome(StrEnum):
    """经过支付渠道验签后归一化的最终支付事件类型。"""

    PAID = "paid"
    FAILED = "failed"
    EXPIRED = "expired"
    PENDING = "pending"


@dataclass(frozen=True)
class VerifiedPaymentEvent:
    """支付模块传给会员模块的标准化事件，不包含 Stripe SDK 对象。"""

    event_id: str
    outcome: PaymentEventOutcome
    session_id: str
    order_reference: str | None
    client_reference_id: str | None
    metadata_user_id: str | None
    metadata_plan_id: str | None
    mode: str | None
    currency: str | None
    amount_total: int | None
    is_live: bool
    is_payment_settled: bool
    session_has_expired: bool
    confirmed_at: datetime


@dataclass(frozen=True)
class PaymentOrderContext:
    """会员模块提供给支付模块的最小 Checkout 订单上下文。"""

    order_id: int
    user_id: int
    plan_id: int
    plan_name: str
    amount: Decimal
    duration_days: int
    status: str
    stripe_session_id: str | None


@dataclass(frozen=True)
class MembershipGrantResult:
    """管理员赠送会员成功后的订单和有效期摘要。"""

    order_id: str
    user_id: int
    email: str
    plan_name: str
    starts_at: datetime
    expires_at: datetime
    already_applied: bool
