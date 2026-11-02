"""提供支付 Router 所需的会员服务、Stripe 适配器和配置依赖。"""

from typing import Annotated

from fastapi import Depends

from app.core.config import Settings, get_settings
from app.infrastructure.payments.stripe_checkout import StripeCheckoutAdapter
from app.modules.membership.dependencies import MembershipServiceDependency
from app.modules.payment.service import PaymentService


def get_payment_service(
    membership_service: MembershipServiceDependency,
    settings: Annotated[Settings, Depends(get_settings)],
) -> PaymentService:
    """组合会员应用服务与 Stripe 基础设施适配器。"""

    return PaymentService(membership_service, StripeCheckoutAdapter(settings))


PaymentServiceDependency = Annotated[PaymentService, Depends(get_payment_service)]
