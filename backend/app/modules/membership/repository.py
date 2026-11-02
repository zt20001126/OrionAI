"""封装会员套餐、订单和期限的 SQLAlchemy 查询与持久化。"""

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.auth.models import User
from app.modules.membership.constants import MembershipOrderStatus, MembershipOrderType
from app.modules.membership.models import Membership, MembershipOrder, MembershipPlan


def list_enabled_plans(session: Session) -> list[MembershipPlan]:
    """按价格升序读取前台可售套餐。"""

    statement = (
        select(MembershipPlan)
        .where(MembershipPlan.is_enabled.is_(True))
        .order_by(MembershipPlan.duration_days.asc(), MembershipPlan.id.asc())
    )
    return list(session.scalars(statement))


def get_plan(session: Session, plan_id: int, *, enabled_only: bool) -> MembershipPlan | None:
    """按 ID 读取套餐，可选择只接受启用状态。"""

    statement = select(MembershipPlan).where(MembershipPlan.id == plan_id)
    if enabled_only:
        statement = statement.where(MembershipPlan.is_enabled.is_(True))
    return session.scalar(statement)


def get_plan_by_name(
    session: Session,
    name: str,
    *,
    enabled_only: bool,
) -> MembershipPlan | None:
    """按套餐稳定名称读取套餐，可要求仅返回启用项。"""

    statement = select(MembershipPlan).where(MembershipPlan.name == name)
    if enabled_only:
        statement = statement.where(MembershipPlan.is_enabled.is_(True))
    return session.scalar(statement)


def get_registered_user_by_account(
    session: Session,
    account: str,
    *,
    for_update: bool = False,
) -> User | None:
    """按规范化邮箱读取注册用户，并可锁定用户行以串行化会员排期。"""

    statement = select(User).where(func.lower(User.account) == account, User.is_guest.is_(False))
    if for_update:
        statement = statement.with_for_update()
    return session.scalar(statement)


def get_order_by_request(
    session: Session,
    user_id: int,
    request_id: str,
) -> MembershipOrder | None:
    """按用户和幂等键读取已有订单。"""

    statement = select(MembershipOrder).where(
        MembershipOrder.user_id == user_id,
        MembershipOrder.request_id == request_id,
    )
    return session.scalar(statement)


def create_order(
    session: Session,
    *,
    user_id: int,
    plan: MembershipPlan,
    request_id: str,
) -> MembershipOrder:
    """以套餐当前价格和有效天数快照新增会员订单。"""

    order = MembershipOrder(
        user_id=user_id,
        plan_id=plan.id,
        amount=plan.price,
        duration_days=plan.duration_days,
        request_id=request_id,
    )
    session.add(order)
    session.flush()
    return order


def create_manual_grant_order(
    session: Session,
    *,
    user_id: int,
    plan: MembershipPlan,
    request_id: str,
    reason: str,
) -> MembershipOrder:
    """创建金额为零且带赠送原因的后台会员发放记录。"""

    order = MembershipOrder(
        user_id=user_id,
        plan_id=plan.id,
        amount=0,
        duration_days=plan.duration_days,
        request_id=request_id,
        order_type=MembershipOrderType.MANUAL_GRANT,
        grant_reason=reason,
        status=MembershipOrderStatus.PAID,
    )
    session.add(order)
    session.flush()
    return order


def get_order(
    session: Session,
    order_id: int,
    *,
    user_id: int | None = None,
    for_update: bool = False,
) -> MembershipOrder | None:
    """读取订单，可限制用户归属并在支付状态流转时锁行。"""

    statement = select(MembershipOrder).where(MembershipOrder.id == order_id)
    if user_id is not None:
        statement = statement.where(MembershipOrder.user_id == user_id)
    if for_update:
        statement = statement.with_for_update()
    return session.scalar(statement)


def get_order_with_plan(
    session: Session,
    order_id: int,
    user_id: int,
) -> tuple[MembershipOrder, MembershipPlan] | None:
    """仅在订单所属用户范围内读取订单与套餐名称。"""

    statement = (
        select(MembershipOrder, MembershipPlan)
        .join(MembershipPlan, MembershipPlan.id == MembershipOrder.plan_id)
        .where(MembershipOrder.id == order_id, MembershipOrder.user_id == user_id)
    )
    row = session.execute(statement).one_or_none()
    return row if row is not None else None


def list_orders(
    session: Session,
    user_id: int,
    *,
    limit: int,
    offset: int,
) -> list[tuple[MembershipOrder, MembershipPlan]]:
    """按创建时间倒序分页读取本人订单及套餐名称。"""

    statement = (
        select(MembershipOrder, MembershipPlan)
        .join(MembershipPlan, MembershipPlan.id == MembershipOrder.plan_id)
        .where(MembershipOrder.user_id == user_id)
        .order_by(MembershipOrder.created_at.desc(), MembershipOrder.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(session.execute(statement))


def count_orders(session: Session, user_id: int) -> int:
    """统计本人会员订单总数。"""

    statement = (
        select(func.count()).select_from(MembershipOrder).where(MembershipOrder.user_id == user_id)
    )
    return session.scalar(statement) or 0


def list_periods(
    session: Session, user_id: int
) -> list[tuple[Membership, MembershipOrder, MembershipPlan]]:
    """按开始时间升序读取会员期限及其订单套餐信息。"""

    statement = (
        select(Membership, MembershipOrder, MembershipPlan)
        .join(MembershipOrder, MembershipOrder.id == Membership.order_id)
        .join(MembershipPlan, MembershipPlan.id == MembershipOrder.plan_id)
        .where(Membership.user_id == user_id)
        .order_by(Membership.starts_at.asc(), Membership.order_id.asc())
    )
    return list(session.execute(statement))


def get_access_period(
    session: Session,
    user_id: int,
    *,
    now: datetime,
) -> tuple[datetime, datetime] | None:
    """读取当前或最近未来会员期限，供准入缓存计算下一状态边界。"""

    statement = (
        select(Membership.starts_at, Membership.expires_at)
        .where(Membership.user_id == user_id, Membership.expires_at > now)
        .order_by(Membership.starts_at.asc(), Membership.order_id.asc())
        .limit(1)
    )
    row = session.execute(statement).one_or_none()
    return (row.starts_at, row.expires_at) if row is not None else None


def lock_user(session: Session, user_id: int) -> int | None:
    """锁定用户行，串行化同一用户并发会员入账的排期计算。"""

    statement = select(User.id).where(User.id == user_id).with_for_update()
    return session.scalar(statement)


def latest_period_expiry(session: Session, user_id: int) -> datetime | None:
    """读取当前用户所有已购买期限的最大结束时间。"""

    statement = select(func.max(Membership.expires_at)).where(Membership.user_id == user_id)
    return session.scalar(statement)


def create_period(
    session: Session,
    *,
    order_id: int,
    user_id: int,
    starts_at: datetime,
    expires_at: datetime,
) -> Membership:
    """为成功订单新增一段会员有效期限。"""

    membership = Membership(
        order_id=order_id,
        user_id=user_id,
        starts_at=starts_at,
        expires_at=expires_at,
    )
    session.add(membership)
    session.flush()
    return membership


def set_checkout_session(order: MembershipOrder, session_id: str) -> None:
    """绑定订单唯一 Stripe Checkout Session ID。"""

    order.stripe_session_id = session_id


def mark_order_status(
    order: MembershipOrder,
    status: str,
    *,
    paid_at: datetime | None = None,
) -> None:
    """更新订单状态并在确认成功时记录服务端确认时间。"""

    order.status = status
    if paid_at is not None:
        order.paid_at = paid_at


def get_period_by_order(session: Session, order_id: int) -> Membership | None:
    """检查订单是否已经生成会员期限，用于 Webhook 幂等防护。"""

    return session.get(Membership, order_id)
