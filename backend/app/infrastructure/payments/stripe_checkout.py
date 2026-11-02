"""封装 Stripe Checkout Session 和 Webhook 签名验证，不访问业务数据库。"""

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from app.core.config import Settings
from app.modules.membership.dto import PaymentEventOutcome, VerifiedPaymentEvent

STRIPE_CURRENCY = "cny"
STRIPE_CHECKOUT_MODE = "payment"
STRIPE_CHECKOUT_EXPIRY_SECONDS = 24 * 60 * 60
STRIPE_IDEMPOTENCY_PREFIX = "orionai-membership-order-"
STRIPE_ORDER_METADATA_KEY = "order_id"
STRIPE_USER_METADATA_KEY = "user_id"
STRIPE_PLAN_METADATA_KEY = "plan_id"
STRIPE_PAID_PAYMENT_STATUS = "paid"
STRIPE_EXPIRED_SESSION_STATUS = "expired"
STRIPE_SUCCESS_PATH = "/membership"
STRIPE_CANCEL_PATH = "/membership/checkout"


class StripeGatewayError(Exception):
    """Stripe SDK 或远端 API 调用失败。"""


class StripeSignatureError(Exception):
    """Stripe Webhook 签名缺失、无效或请求体格式错误。"""


class StripeConfigurationError(Exception):
    """Stripe SDK 未安装或当前支付凭据未完成配置。"""


@dataclass(frozen=True)
class StripeCheckoutSession:
    """从 Stripe Checkout Session 中提取的有限字段。"""

    session_id: str
    url: str | None
    expires_at: datetime
    status: str | None
    payment_status: str | None
    client_reference_id: str | None
    metadata_order_id: str | None
    metadata_user_id: str | None
    metadata_plan_id: str | None
    mode: str | None
    currency: str | None
    amount_total: int | None
    is_live: bool


def _read_field(source: Any, name: str, default: Any = None) -> Any:
    """兼容 StripeObject 和映射对象读取字段。"""

    if isinstance(source, dict):
        return source.get(name, default)
    return getattr(source, name, default)


def _session_summary(source: Any) -> StripeCheckoutSession:
    """将 SDK Session 限定转换为支付应用可消费的内部对象。"""

    session_id = _read_field(source, "id")
    expiry_timestamp = _read_field(source, "expires_at")
    if (
        not isinstance(session_id, str)
        or not session_id
        or isinstance(expiry_timestamp, bool)
        or not isinstance(expiry_timestamp, int)
    ):
        raise StripeGatewayError("Stripe 返回的 Checkout Session 字段不完整。")
    metadata = _read_field(source, "metadata", {})
    amount_total = _read_field(source, "amount_total")
    if isinstance(amount_total, bool) or not isinstance(amount_total, int):
        amount_total = None
    return StripeCheckoutSession(
        session_id=session_id,
        url=_read_field(source, "url"),
        expires_at=datetime.fromtimestamp(expiry_timestamp, tz=UTC),
        status=_read_field(source, "status"),
        payment_status=_read_field(source, "payment_status"),
        client_reference_id=_read_field(source, "client_reference_id"),
        metadata_order_id=_read_field(metadata, STRIPE_ORDER_METADATA_KEY),
        metadata_user_id=_read_field(metadata, STRIPE_USER_METADATA_KEY),
        metadata_plan_id=_read_field(metadata, STRIPE_PLAN_METADATA_KEY),
        mode=_read_field(source, "mode"),
        currency=_read_field(source, "currency"),
        amount_total=amount_total,
        is_live=_read_field(source, "livemode", True) is not False,
    )


class StripeCheckoutAdapter:
    """按请求实例持有 Stripe 测试密钥并转换第三方 SDK 对象。"""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    @property
    def configured(self) -> bool:
        """仅在 Sandbox API 密钥与 Webhook 密钥都存在时开放支付。"""

        return self._settings.stripe_checkout_configured

    def create_session(
        self,
        *,
        order_id: int,
        user_id: int,
        plan_id: int,
        plan_name: str,
        amount: Decimal,
    ) -> StripeCheckoutSession:
        """创建有固定到期时间和稳定订单级幂等键的 Stripe Checkout Session。"""

        client = self._stripe_client()
        amount_in_minor_units = int((amount * Decimal("100")).to_integral_exact())
        frontend_base_url = self._settings.membership_frontend_base_url
        params = {
            "mode": STRIPE_CHECKOUT_MODE,
            "line_items": [
                {
                    "quantity": 1,
                    "price_data": {
                        "currency": STRIPE_CURRENCY,
                        "unit_amount": amount_in_minor_units,
                        "product_data": {"name": f"OrionAI 会员 · {plan_name}"},
                    },
                }
            ],
            "client_reference_id": str(order_id),
            "metadata": {
                STRIPE_ORDER_METADATA_KEY: str(order_id),
                STRIPE_USER_METADATA_KEY: str(user_id),
                STRIPE_PLAN_METADATA_KEY: str(plan_id),
            },
            "success_url": (
                f"{frontend_base_url}{STRIPE_SUCCESS_PATH}?order_id={order_id}"
                "&session_id={CHECKOUT_SESSION_ID}"
            ),
            "cancel_url": (
                f"{frontend_base_url}{STRIPE_CANCEL_PATH}/{plan_id}/order/{order_id}"
                "?payment=cancelled"
            ),
            "expires_at": int(datetime.now(UTC).timestamp())
            + STRIPE_CHECKOUT_EXPIRY_SECONDS,
        }
        try:
            stripe_session = client.v1.checkout.sessions.create(
                params,
                options={"idempotency_key": f"{STRIPE_IDEMPOTENCY_PREFIX}{order_id}"},
            )
        except Exception as error:
            if self._is_stripe_error(error):
                raise StripeGatewayError("Stripe Checkout Session 创建失败。") from error
            raise
        return _session_summary(stripe_session)

    def retrieve_session(self, session_id: str) -> StripeCheckoutSession:
        """通过已保存的 Stripe Session ID 重新获取当前支付 URL 和状态。"""

        client = self._stripe_client()
        try:
            stripe_session = client.v1.checkout.sessions.retrieve(session_id)
        except Exception as error:
            if self._is_stripe_error(error):
                raise StripeGatewayError("Stripe Checkout Session 查询失败。") from error
            raise
        return _session_summary(stripe_session)

    def verify_webhook(self, payload: bytes, signature: str) -> VerifiedPaymentEvent | None:
        """验证 Stripe-Signature 并把受支持事件映射为不含原始载荷的内部对象。"""

        stripe = self._load_stripe_module()
        webhook_secret = self._settings.stripe_webhook_secret.get_secret_value().strip()
        if not webhook_secret:
            raise StripeConfigurationError("Stripe Webhook 尚未配置。")
        try:
            stripe_event = stripe.Webhook.construct_event(payload, signature, webhook_secret)
        except (ValueError, stripe.SignatureVerificationError) as error:
            raise StripeSignatureError("Stripe Webhook 签名无效。") from error

        event_type = _read_field(stripe_event, "type")
        if not self._is_supported_event_type(event_type):
            return None

        event_data = _read_field(stripe_event, "data")
        session = _read_field(event_data, "object")
        metadata = _read_field(session, "metadata", {})
        event_id = _read_field(stripe_event, "id", "")
        session_id = _read_field(session, "id")
        if not isinstance(session_id, str) or not session_id:
            raise StripeSignatureError("Stripe Webhook Session 字段无效。")

        amount_total = _read_field(session, "amount_total")
        if isinstance(amount_total, bool) or not isinstance(amount_total, int):
            amount_total = None
        payment_status = _read_field(session, "payment_status")
        session_status = _read_field(session, "status")
        outcome = self._event_outcome(
            event_type,
            payment_status=payment_status,
            session_status=session_status,
        )

        return VerifiedPaymentEvent(
            event_id=str(event_id),
            outcome=outcome,
            session_id=session_id,
            order_reference=_read_field(metadata, STRIPE_ORDER_METADATA_KEY),
            client_reference_id=_read_field(session, "client_reference_id"),
            metadata_user_id=_read_field(metadata, STRIPE_USER_METADATA_KEY),
            metadata_plan_id=_read_field(metadata, STRIPE_PLAN_METADATA_KEY),
            mode=_read_field(session, "mode"),
            currency=_read_field(session, "currency"),
            amount_total=amount_total,
            is_live=_read_field(session, "livemode", True) is not False,
            is_payment_settled=payment_status == STRIPE_PAID_PAYMENT_STATUS,
            session_has_expired=session_status == STRIPE_EXPIRED_SESSION_STATUS,
            confirmed_at=datetime.now(UTC),
        )

    def _stripe_client(self) -> Any:
        """构造 Stripe SDK 客户端；环境未配置时不发起远端调用。"""

        if not self.configured:
            raise StripeConfigurationError("Stripe Sandbox 尚未完成支付和 Webhook 配置。")
        stripe = self._load_stripe_module()
        secret_key = self._settings.stripe_secret_key.get_secret_value().strip()
        return stripe.StripeClient(secret_key, max_network_retries=2)

    @staticmethod
    def _load_stripe_module() -> Any:
        """延迟载入 Stripe SDK，允许未配置支付的本地环境启动应用。"""

        try:
            import stripe
        except ImportError as error:
            raise StripeConfigurationError("Stripe SDK 未安装，请安装后端依赖。") from error
        return stripe

    @staticmethod
    def _is_stripe_error(error: Exception) -> bool:
        """只把 Stripe SDK 错误转换为支付网关错误，保留程序缺陷的原始异常。"""

        stripe = StripeCheckoutAdapter._load_stripe_module()
        return isinstance(error, stripe.StripeError)

    @staticmethod
    def _is_supported_event_type(event_type: str | None) -> bool:
        """确认事件属于当前 Checkout Session Webhook 处理范围。"""

        return event_type in {
            "checkout.session.completed",
            "checkout.session.async_payment_succeeded",
            "checkout.session.async_payment_failed",
            "checkout.session.expired",
        }

    @staticmethod
    def _event_outcome(
        event_type: str | None,
        *,
        payment_status: str | None,
        session_status: str | None,
    ) -> PaymentEventOutcome:
        """基于 Stripe 最终支付状态和 Session 状态归一事件结果。"""

        if payment_status == STRIPE_PAID_PAYMENT_STATUS:
            return PaymentEventOutcome.PAID
        if event_type == "checkout.session.async_payment_failed":
            return PaymentEventOutcome.FAILED
        if (
            event_type == "checkout.session.expired"
            and session_status == STRIPE_EXPIRED_SESSION_STATUS
        ):
            return PaymentEventOutcome.EXPIRED
        return PaymentEventOutcome.PENDING
