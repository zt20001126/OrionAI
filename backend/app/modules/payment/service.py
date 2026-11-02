"""编排 Stripe Checkout、支付方式发现和 Webhook 事件分发。"""

import logging
from datetime import UTC, datetime
from urllib.parse import urlsplit

from app.infrastructure.payments.stripe_checkout import (
    StripeCheckoutAdapter,
    StripeCheckoutSession,
    StripeConfigurationError,
    StripeGatewayError,
)
from app.infrastructure.payments.stripe_checkout import (
    StripeSignatureError as StripeAdapterSignatureError,
)
from app.modules.membership.constants import MembershipOrderStatus
from app.modules.membership.dto import PaymentEventOutcome, PaymentOrderContext
from app.modules.membership.errors import (
    MembershipConflictError,
    MembershipNotFoundError,
    MembershipUnavailableError,
)
from app.modules.membership.service import MembershipService
from app.modules.payment.errors import (
    PaymentConflictError,
    PaymentMethodUnavailableError,
    PaymentSignatureError,
    PaymentUnavailableError,
)
from app.modules.payment.schemas import CheckoutSessionResponse, PaymentMethodResponse

logger = logging.getLogger(__name__)
STRIPE_METHOD_CODE = "stripe"
STRIPE_METHOD_NAME = "Stripe 支付"
STRIPE_METHOD_DESCRIPTION = "通过 Stripe Checkout 安全完成银行卡支付"
STRIPE_SESSION_OPEN_STATUS = "open"
STRIPE_SESSION_EXPIRED_STATUS = "expired"


class PaymentService:
    """执行业务支付流程并把验签后的标准事件交由会员模块处理。"""

    def __init__(
        self,
        membership_service: MembershipService,
        stripe_adapter: StripeCheckoutAdapter,
    ) -> None:
        self._membership = membership_service
        self._stripe = stripe_adapter

    def list_payment_methods(self) -> list[PaymentMethodResponse]:
        """只公开当前同时具备支付密钥和 Webhook 密钥的渠道。"""

        if not self._stripe.configured:
            return []
        return [
            PaymentMethodResponse(
                code=STRIPE_METHOD_CODE,
                name=STRIPE_METHOD_NAME,
                description=STRIPE_METHOD_DESCRIPTION,
            )
        ]

    def create_checkout_session(
        self,
        *,
        user_id: int,
        order_id: int,
        payment_method: str,
    ) -> CheckoutSessionResponse:
        """为本人待支付订单创建或恢复 Stripe Checkout Session。

        Step 1: 校验支付渠道、订单归属、订单状态和后端价格快照。
        Step 2: 有 Session ID 时向 Stripe 读取当前 Session；否则以订单级幂等键创建。
        Step 3: 只持久化 Session ID，并将 Stripe 托管 URL 返回给前端。
        """

        if payment_method != STRIPE_METHOD_CODE:
            raise PaymentMethodUnavailableError
        if not self._stripe.configured:
            raise PaymentUnavailableError
        try:
            order = self._membership.get_payment_context(user_id=user_id, order_id=order_id)
            if order.status != MembershipOrderStatus.PENDING:
                raise PaymentConflictError("当前订单状态不能继续支付，请重新选择套餐。")

            if order.stripe_session_id is not None:
                session = self._stripe.retrieve_session(order.stripe_session_id)
                self._validate_session_identity(session, order)
                if (
                    session.status == STRIPE_SESSION_EXPIRED_STATUS
                    or session.expires_at <= datetime.now(UTC)
                ):
                    self._membership.mark_checkout_session_expired(
                        user_id=user_id,
                        order_id=order_id,
                        session_id=order.stripe_session_id,
                    )
                    raise PaymentConflictError("支付链接已过期，请重新选择套餐。")
                if session.status != STRIPE_SESSION_OPEN_STATUS or not session.url:
                    raise PaymentConflictError("支付结果正在确认，请稍后刷新订单状态。")
                return self._response(order_id, session)

            session = self._stripe.create_session(
                order_id=order.order_id,
                user_id=order.user_id,
                plan_id=order.plan_id,
                plan_name=order.plan_name,
                amount=order.amount,
            )
            self._validate_session_identity(session, order)
            self._membership.attach_checkout_session(
                user_id=user_id,
                order_id=order_id,
                session_id=session.session_id,
            )
            if (
                session.status == STRIPE_SESSION_EXPIRED_STATUS
                or session.expires_at <= datetime.now(UTC)
            ):
                self._membership.mark_checkout_session_expired(
                    user_id=user_id,
                    order_id=order_id,
                    session_id=session.session_id,
                )
                raise PaymentConflictError("支付链接已过期，请重新选择套餐。")
            if session.status != STRIPE_SESSION_OPEN_STATUS:
                raise PaymentConflictError("支付结果正在确认，请稍后刷新订单状态。")
            self._validate_checkout_url(session)
            return self._response(order_id, session)
        except PaymentConflictError:
            raise
        except MembershipNotFoundError:
            raise MembershipNotFoundError from None
        except MembershipConflictError as error:
            raise PaymentConflictError(error.detail) from None
        except MembershipUnavailableError:
            raise PaymentUnavailableError from None
        except StripeConfigurationError:
            logger.exception("stripe_checkout_configuration_failed order_id=%s", order_id)
            raise PaymentUnavailableError from None
        except StripeGatewayError:
            logger.exception("stripe_checkout_request_failed order_id=%s", order_id)
            raise PaymentUnavailableError from None

    def handle_webhook(self, *, payload: bytes, signature: str) -> bool:
        """验签后分发 Checkout 结果；未知和无法关联事件按策略确认接收。"""

        try:
            event = self._stripe.verify_webhook(payload, signature)
        except StripeAdapterSignatureError:
            raise PaymentSignatureError from None
        except (StripeConfigurationError, StripeGatewayError):
            logger.exception("stripe_webhook_verification_unavailable")
            raise PaymentUnavailableError from None

        if event is None:
            logger.info("stripe_webhook_ignored_unsupported_event")
            return True
        if event.outcome == PaymentEventOutcome.PENDING:
            logger.info("stripe_webhook_received_pending event_id=%s", event.event_id)
        try:
            return self._membership.apply_verified_payment_event(event)
        except MembershipUnavailableError:
            raise PaymentUnavailableError from None

    @staticmethod
    def _validate_session_identity(
        session: StripeCheckoutSession,
        order: PaymentOrderContext,
    ) -> None:
        """确保 Stripe Session 与本地订单、用户、套餐和成交金额完全一致。"""

        expected_amount = int((order.amount * 100).to_integral_exact())
        if not all(
            (
                order.stripe_session_id is None or session.session_id == order.stripe_session_id,
                session.client_reference_id == str(order.order_id),
                session.metadata_order_id == str(order.order_id),
                session.metadata_user_id == str(order.user_id),
                session.metadata_plan_id == str(order.plan_id),
                session.mode == "payment",
                session.currency == "cny",
                session.amount_total == expected_amount,
                not session.is_live,
            )
        ):
            raise PaymentUnavailableError

    @staticmethod
    def _validate_checkout_url(session: StripeCheckoutSession) -> None:
        """只向浏览器返回 Stripe 提供的 HTTPS Checkout 地址。"""

        parsed = urlsplit(session.url or "")
        if parsed.scheme != "https" or not parsed.netloc:
            raise PaymentUnavailableError

    @staticmethod
    def _response(order_id: int, session: StripeCheckoutSession) -> CheckoutSessionResponse:
        """转换适配器 Session 为公开 API 响应，不保存支付 URL。"""

        if session.url is None:
            raise PaymentConflictError("支付链接当前不可用，请稍后重试。")
        return CheckoutSessionResponse(
            order_id=str(order_id),
            checkout_url=session.url,
            expires_at=session.expires_at,
        )
