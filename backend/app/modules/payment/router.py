"""定义支付渠道发现、Checkout Session 和 Stripe Webhook API。"""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from app.modules.auth.dependencies import RegisteredUser, validate_origin
from app.modules.payment.dependencies import PaymentServiceDependency
from app.modules.payment.schemas import (
    CheckoutSessionResponse,
    CreateCheckoutSessionRequest,
    PaymentMethodResponse,
    StripeCheckoutSessionRequest,
    StripeWebhookAcknowledgement,
)
from app.modules.payment.service import STRIPE_METHOD_CODE

router = APIRouter(prefix="/v1/payments", tags=["payments"])
webhook_router = APIRouter(prefix="/payments", tags=["payment-webhooks"])
MAX_STRIPE_WEBHOOK_BYTES = 1_048_576


@router.get("/methods", response_model=list[PaymentMethodResponse])
def list_payment_methods(
    service: PaymentServiceDependency,
) -> list[PaymentMethodResponse]:
    """返回当前环境已完整配置的支付渠道。"""

    return service.list_payment_methods()


@router.post(
    "/checkout-sessions",
    response_model=CheckoutSessionResponse,
    dependencies=[Depends(validate_origin)],
)
def create_checkout_session(
    payload: CreateCheckoutSessionRequest,
    user: RegisteredUser,
    service: PaymentServiceDependency,
) -> CheckoutSessionResponse:
    """按客户端选中的可用支付方式创建或恢复支付会话。"""

    return service.create_checkout_session(
        user_id=user.id,
        order_id=int(payload.order_id),
        payment_method=payload.payment_method,
    )


@router.post(
    "/stripe/checkout-sessions",
    response_model=CheckoutSessionResponse,
    dependencies=[Depends(validate_origin)],
)
def create_stripe_checkout_session(
    payload: StripeCheckoutSessionRequest,
    user: RegisteredUser,
    service: PaymentServiceDependency,
) -> CheckoutSessionResponse:
    """提供方案中 Stripe 专用的 Checkout Session API。"""

    return service.create_checkout_session(
        user_id=user.id,
        order_id=int(payload.order_id),
        payment_method=STRIPE_METHOD_CODE,
    )


@webhook_router.post("/stripe/webhook", response_model=StripeWebhookAcknowledgement)
async def receive_stripe_webhook(
    request: Request,
    service: PaymentServiceDependency,
    signature: Annotated[str | None, Header(alias="Stripe-Signature")] = None,
) -> StripeWebhookAcknowledgement:
    """读取有大小限制的原始请求体并交由支付服务验签处理。"""

    if signature is None:
        raise HTTPException(status_code=400, detail="Stripe Webhook 签名无效。")

    payload = bytearray()
    async for chunk in request.stream():
        if len(payload) + len(chunk) > MAX_STRIPE_WEBHOOK_BYTES:
            raise HTTPException(status_code=413, detail="Stripe Webhook 请求体过大。")
        payload.extend(chunk)

    service.handle_webhook(payload=bytes(payload), signature=signature)
    return StripeWebhookAcknowledgement(received=True)
