"""验证 Stripe Checkout 入参快照和已验签 Webhook 的内部转换。"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
import stripe
from pydantic import ValidationError

from app.core.config import Settings
from app.infrastructure.payments.stripe_checkout import StripeCheckoutAdapter
from app.modules.membership.dto import PaymentEventOutcome


def _settings() -> Settings:
    """构造只用于单测的 Stripe Sandbox 配置。"""

    return Settings(
        stripe_secret_key="sk_test_unit",
        stripe_webhook_secret="whsec_unit",
        membership_frontend_base_url="https://orionai.example",
    )


def test_membership_payment_rejects_live_stripe_secret() -> None:
    """首期配置只允许 Sandbox 密钥，避免误用生产支付凭据。"""

    with pytest.raises(ValidationError):
        Settings(stripe_secret_key="sk_live_not_allowed")


def test_checkout_creation_uses_server_amount_metadata_and_stable_idempotency_key(
    monkeypatch,
) -> None:
    """Checkout 金额来自订单快照，回跳地址受服务端配置控制。"""

    expires_at = datetime.now(UTC) + timedelta(hours=1)
    session_result = {
        "id": "cs_membership_test",
        "url": "https://checkout.stripe.com/session",
        "expires_at": int(expires_at.timestamp()),
        "status": "open",
        "payment_status": "unpaid",
        "client_reference_id": "12345",
        "metadata": {"order_id": "12345", "user_id": "678", "plan_id": "9"},
        "mode": "payment",
        "currency": "cny",
        "amount_total": 9990,
        "livemode": False,
    }

    class FakeSessions:
        params = None
        options = None

        def create(self, params, options):
            self.params = params
            self.options = options
            return session_result

    sessions = FakeSessions()
    fake_client = SimpleNamespace(v1=SimpleNamespace(checkout=SimpleNamespace(sessions=sessions)))
    monkeypatch.setattr(stripe, "StripeClient", lambda *_args, **_kwargs: fake_client)

    session = StripeCheckoutAdapter(_settings()).create_session(
        order_id=12345,
        user_id=678,
        plan_id=9,
        plan_name="季度会员",
        amount=Decimal("99.90"),
    )

    assert sessions.params["line_items"][0]["price_data"]["unit_amount"] == 9990
    assert sessions.params["line_items"][0]["price_data"]["currency"] == "cny"
    assert sessions.params["success_url"].startswith("https://orionai.example/membership?")
    assert sessions.params["cancel_url"].startswith(
        "https://orionai.example/membership/checkout/9/order/12345"
    )
    assert sessions.options == {"idempotency_key": "orionai-membership-order-12345"}
    assert session.session_id == "cs_membership_test"
    assert session.amount_total == 9990
    assert not session.is_live


def test_verified_checkout_webhook_is_normalized_without_exposing_raw_event(monkeypatch) -> None:
    """Webhook 适配器只输出已验签 Checkout 事件所需的最小字段。"""

    event_payload = {
        "id": "evt_membership_test",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_membership_test",
                "client_reference_id": "12345",
                "metadata": {"order_id": "12345", "user_id": "678", "plan_id": "9"},
                "mode": "payment",
                "status": "complete",
                "currency": "cny",
                "amount_total": 9990,
                "payment_status": "paid",
                "livemode": False,
            }
        },
    }
    monkeypatch.setattr(
        stripe.Webhook,
        "construct_event",
        staticmethod(lambda _payload, _signature, _secret: event_payload),
    )

    event = StripeCheckoutAdapter(_settings()).verify_webhook(b"signed body", "t=1,v1=valid")

    assert event is not None
    assert event.event_id == "evt_membership_test"
    assert event.outcome == PaymentEventOutcome.PAID
    assert event.order_reference == "12345"
    assert event.metadata_user_id == "678"
    assert event.amount_total == 9990
    assert event.is_live is False
    assert event.is_payment_settled
    assert not event.session_has_expired
