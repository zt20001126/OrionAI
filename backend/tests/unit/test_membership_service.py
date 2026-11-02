"""验证会员下单幂等、支付入账和固定期限顺延规则。"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.infrastructure.database.base import Base
from app.modules.auth.models import User
from app.modules.membership.dto import PaymentEventOutcome, VerifiedPaymentEvent
from app.modules.membership.errors import MembershipConflictError, MembershipNotFoundError
from app.modules.membership.models import Membership, MembershipOrder, MembershipPlan
from app.modules.membership.service import MembershipService


@pytest.fixture
def membership_session():
    """使用隔离的 SQLite 数据库验证会员用例，不连接项目配置的业务数据库。"""

    engine = create_engine("sqlite+pysqlite:///:memory:")
    tables = [
        User.__table__,
        MembershipPlan.__table__,
        MembershipOrder.__table__,
        Membership.__table__,
    ]
    Base.metadata.create_all(engine, tables=tables)
    with Session(engine) as session:
        user = User(account="member@example.test", password_hash="test-hash", is_guest=False)
        monthly = MembershipPlan(
            id=1001,
            name="月度会员",
            price=Decimal("9.90"),
            duration_days=30,
            is_enabled=True,
        )
        quarterly = MembershipPlan(
            id=1002,
            name="季度会员",
            price=Decimal("99.90"),
            duration_days=90,
            is_enabled=True,
        )
        disabled = MembershipPlan(
            id=1003,
            name="停用会员",
            price=Decimal("19.90"),
            duration_days=30,
            is_enabled=False,
        )
        session.add_all([user, monthly, quarterly, disabled])
        session.commit()
        session.refresh(user)
        yield session, user, monthly, quarterly, disabled
    engine.dispose()


def _event(
    *,
    order: MembershipOrder,
    user: User,
    plan: MembershipPlan,
    session_id: str,
    amount_total: int,
    confirmed_at: datetime,
    outcome: PaymentEventOutcome = PaymentEventOutcome.PAID,
) -> VerifiedPaymentEvent:
    """构造 Stripe 适配器已验签后交给会员模块的标准事件。"""

    return VerifiedPaymentEvent(
        event_id=f"evt_{session_id}",
        outcome=outcome,
        session_id=session_id,
        order_reference=str(order.id),
        client_reference_id=str(order.id),
        metadata_user_id=str(user.id),
        metadata_plan_id=str(plan.id),
        mode="payment",
        currency="cny",
        amount_total=amount_total,
        is_live=False,
        is_payment_settled=outcome == PaymentEventOutcome.PAID,
        session_has_expired=outcome == PaymentEventOutcome.EXPIRED,
        confirmed_at=confirmed_at,
    )


def test_order_creation_is_idempotent_and_snapshots_plan(membership_session) -> None:
    """相同用户和请求键复用订单及价格快照，不同套餐复用键返回冲突。"""

    session, user, monthly, quarterly, _disabled = membership_session
    service = MembershipService(session)
    request_id = uuid4()

    created = service.create_order(user_id=user.id, plan_id=monthly.id, request_id=request_id)
    monthly.price = Decimal("12.50")
    session.commit()
    retried = service.create_order(user_id=user.id, plan_id=monthly.id, request_id=request_id)

    assert retried.order_id == created.order_id
    assert retried.amount == "9.90"
    assert retried.duration_days == 30
    with pytest.raises(MembershipConflictError):
        service.create_order(user_id=user.id, plan_id=quarterly.id, request_id=request_id)


def test_disabled_plan_cannot_create_new_order(membership_session) -> None:
    """停用套餐不允许创建新的支付订单。"""

    session, user, _monthly, _quarterly, disabled = membership_session
    service = MembershipService(session)

    with pytest.raises(MembershipNotFoundError):
        service.create_order(user_id=user.id, plan_id=disabled.id, request_id=uuid4())


def test_paid_orders_extend_period_and_duplicate_webhook_is_idempotent(membership_session) -> None:
    """重复支付通知只发放一次期限，后续购买按上一段到期时间顺延。"""

    session, user, monthly, quarterly, _disabled = membership_session
    confirmed_at = datetime(2026, 11, 2, 12, tzinfo=UTC)
    service = MembershipService(session, clock=lambda: confirmed_at)

    first_response = service.create_order(
        user_id=user.id,
        plan_id=monthly.id,
        request_id=uuid4(),
    )
    first_order = session.get(MembershipOrder, int(first_response.order_id))
    assert first_order is not None
    first_event = _event(
        order=first_order,
        user=user,
        plan=monthly,
        session_id="cs_monthly_1",
        amount_total=990,
        confirmed_at=confirmed_at,
    )
    assert service.apply_verified_payment_event(first_event)
    assert service.apply_verified_payment_event(first_event)

    second_response = service.create_order(
        user_id=user.id,
        plan_id=quarterly.id,
        request_id=uuid4(),
    )
    second_order = session.get(MembershipOrder, int(second_response.order_id))
    assert second_order is not None
    assert service.apply_verified_payment_event(
        _event(
            order=second_order,
            user=user,
            plan=quarterly,
            session_id="cs_quarterly_1",
            amount_total=9990,
            confirmed_at=confirmed_at + timedelta(days=1),
        )
    )

    periods = list(
        session.scalars(
            select(Membership).where(Membership.user_id == user.id).order_by(Membership.starts_at)
        )
    )
    assert len(periods) == 2
    assert periods[1].starts_at == periods[0].expires_at
    assert periods[0].expires_at.replace(tzinfo=UTC) == confirmed_at + timedelta(days=30)
    assert session.get(MembershipOrder, first_order.id).status == "paid"

    overview = service.get_overview(user_id=user.id)
    assert overview.active_period is not None
    assert overview.active_period.order_id == str(first_order.id)
    assert len(overview.upcoming_periods) == 1

    later_service = MembershipService(
        session,
        clock=lambda: periods[1].expires_at + timedelta(days=1),
    )
    expired_overview = later_service.get_overview(user_id=user.id)
    assert expired_overview.active_period is None
    assert expired_overview.latest_expired_period is not None
    assert expired_overview.latest_expired_period.order_id == str(second_order.id)


def test_payment_event_with_mismatched_amount_does_not_grant_membership(membership_session) -> None:
    """金额快照不匹配的已验签事件不得绑定支付会话或授予期限。"""

    session, user, monthly, _quarterly, _disabled = membership_session
    confirmed_at = datetime(2026, 11, 2, 12, tzinfo=UTC)
    service = MembershipService(session, clock=lambda: confirmed_at)
    response = service.create_order(
        user_id=user.id,
        plan_id=monthly.id,
        request_id=uuid4(),
    )
    order = session.get(MembershipOrder, int(response.order_id))
    assert order is not None

    event = _event(
        order=order,
        user=user,
        plan=monthly,
        session_id="cs_wrong_amount",
        amount_total=991,
        confirmed_at=confirmed_at,
    )
    assert not service.apply_verified_payment_event(event)
    session.refresh(order)
    assert order.status == "pending"
    assert order.stripe_session_id is None
    assert session.scalar(select(Membership).where(Membership.order_id == order.id)) is None
