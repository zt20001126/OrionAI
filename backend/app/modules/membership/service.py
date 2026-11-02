"""编排会员套餐、订单、会员期限和付款确认应用用例。"""

import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from redis.exceptions import RedisError
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.modules.membership import repository
from app.modules.membership.access_cache import MembershipAccessCache
from app.modules.membership.constants import (
    MAX_MEMBERSHIP_GRANT_REASON_LENGTH,
    MONTHLY_MEMBERSHIP_DURATION_DAYS,
    MONTHLY_MEMBERSHIP_PLAN_NAME,
    MembershipOrderStatus,
    MembershipOrderType,
)
from app.modules.membership.dto import (
    MembershipGrantResult,
    PaymentEventOutcome,
    PaymentOrderContext,
    VerifiedPaymentEvent,
)
from app.modules.membership.errors import (
    MembershipConflictError,
    MembershipNotFoundError,
    MembershipUnavailableError,
)
from app.modules.membership.models import Membership, MembershipOrder, MembershipPlan
from app.modules.membership.schemas import (
    CreateMembershipOrderResponse,
    MembershipOrderPageResponse,
    MembershipOrderResponse,
    MembershipOverviewResponse,
    MembershipPeriodResponse,
    MembershipPlanResponse,
)

logger = logging.getLogger(__name__)
CENT_AMOUNT_MULTIPLIER = Decimal("100")
MEMBERSHIP_CURRENCY = "cny"
CHECKOUT_MODE = "payment"


def utc_now() -> datetime:
    """返回服务端 UTC 当前时间，便于服务用例注入固定时钟进行验证。"""

    return datetime.now(UTC)


def _as_utc(value: datetime) -> datetime:
    """将数据库返回的时间归一为 UTC；SQLite 测试驱动可能返回无时区值。"""

    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _amount_text(value: Decimal) -> str:
    """以固定两位小数格式返回人民币金额。"""

    return f"{value:.2f}"


def _plan_response(plan: MembershipPlan) -> MembershipPlanResponse:
    """把套餐 ORM 对象转换为公开响应 DTO。"""

    return MembershipPlanResponse(
        id=str(plan.id),
        name=plan.name,
        price=_amount_text(plan.price),
        duration_days=plan.duration_days,
    )


def _order_response(order: MembershipOrder, plan: MembershipPlan) -> MembershipOrderResponse:
    """把订单与套餐 ORM 对象转换为用户可见响应 DTO。"""

    return MembershipOrderResponse(
        order_id=str(order.id),
        plan_id=str(order.plan_id),
        plan_name=plan.name,
        amount=_amount_text(order.amount),
        order_type=MembershipOrderType(order.order_type),
        duration_days=order.duration_days,
        status=MembershipOrderStatus(order.status),
        created_at=order.created_at,
        paid_at=order.paid_at,
    )


def _period_response(
    membership: Membership,
    order: MembershipOrder,
    plan: MembershipPlan,
) -> MembershipPeriodResponse:
    """把会员期限及其套餐名称转换为响应 DTO。"""

    return MembershipPeriodResponse(
        order_id=str(membership.order_id),
        plan_id=str(order.plan_id),
        plan_name=plan.name,
        starts_at=membership.starts_at,
        expires_at=membership.expires_at,
    )


class MembershipService:
    """实现会员下单、状态查询与支付确认后的有效期排期。"""

    def __init__(
        self,
        session: Session,
        *,
        access_cache: MembershipAccessCache | None = None,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._session = session
        self._access_cache = access_cache
        self._clock = clock

    def list_plans(self) -> list[MembershipPlanResponse]:
        """读取启用套餐并返回公开目录。"""

        try:
            return [_plan_response(plan) for plan in repository.list_enabled_plans(self._session)]
        except SQLAlchemyError:
            logger.exception("membership_plan_list_failed")
            raise MembershipUnavailableError from None

    def create_order(
        self,
        *,
        user_id: int,
        plan_id: int,
        request_id: UUID,
    ) -> CreateMembershipOrderResponse:
        """创建用户会员订单。

        Step 1: 按用户和请求键查重，同套餐重试返回既有订单。
        Step 2: 仅对新请求校验套餐启用状态，并快照当前价格和有效天数。
        Step 3: 提交订单；并发幂等冲突时回滚并重新读取获胜订单。
        """

        request_key = str(request_id)
        try:
            existing = repository.get_order_by_request(self._session, user_id, request_key)
            if existing is not None:
                if existing.plan_id != plan_id:
                    raise MembershipConflictError("该请求键已用于其他套餐，请重新发起购买。")
                plan = repository.get_plan(self._session, existing.plan_id, enabled_only=False)
                if plan is None:
                    raise MembershipUnavailableError
                return self._created_order_response(existing)

            plan = repository.get_plan(self._session, plan_id, enabled_only=True)
            if plan is None:
                raise MembershipNotFoundError("会员套餐不存在或已停止销售。")
            order = repository.create_order(
                self._session,
                user_id=user_id,
                plan=plan,
                request_id=request_key,
            )
            self._session.commit()
            self._session.refresh(order)
            return self._created_order_response(order)
        except MembershipConflictError:
            self._session.rollback()
            raise
        except MembershipNotFoundError:
            self._session.rollback()
            raise
        except IntegrityError:
            self._session.rollback()
            # UNIQUE(user_id, request_id) 是并发重试的最终仲裁点。
            raced_order = repository.get_order_by_request(self._session, user_id, request_key)
            if raced_order is not None:
                if raced_order.plan_id != plan_id:
                    raise MembershipConflictError(
                        "该请求键已用于其他套餐，请重新发起购买。"
                    ) from None
                return self._created_order_response(raced_order)
            logger.exception("membership_order_create_integrity_failed user_id=%s", user_id)
            raise MembershipUnavailableError from None
        except SQLAlchemyError:
            self._session.rollback()
            logger.exception("membership_order_create_failed user_id=%s", user_id)
            raise MembershipUnavailableError from None

    def grant_monthly_membership(
        self,
        *,
        email: str,
        reason: str,
        request_id: UUID,
    ) -> MembershipGrantResult:
        """按月度套餐免费发放会员，并将期限排在现有会员之后。

        Step 1: 锁定注册用户并检查月度套餐和赠送原因。
        Step 2: 按幂等请求键复用已完成的赠送，避免脚本重试重复加期。
        Step 3: 创建零金额赠送订单与会员期限并在同一事务提交。
        Step 4: 提交后清除该用户的会员准入缓存。
        """

        normalized_email = email.strip().lower()
        normalized_reason = reason.strip()
        if not normalized_email:
            raise MembershipConflictError("目标邮箱不能为空。")
        if not normalized_reason or len(normalized_reason) > MAX_MEMBERSHIP_GRANT_REASON_LENGTH:
            raise MembershipConflictError("赠送原因不能为空且不能超过 500 个字符。")

        try:
            user = repository.get_registered_user_by_account(
                self._session,
                normalized_email,
                for_update=True,
            )
            if user is None:
                raise MembershipNotFoundError("未找到该邮箱对应的注册用户。")

            plan = repository.get_plan_by_name(
                self._session,
                MONTHLY_MEMBERSHIP_PLAN_NAME,
                enabled_only=True,
            )
            if plan is None or plan.duration_days != MONTHLY_MEMBERSHIP_DURATION_DAYS:
                raise MembershipUnavailableError

            existing_order = repository.get_order_by_request(
                self._session,
                user.id,
                str(request_id),
            )
            if existing_order is not None:
                if (
                    existing_order.order_type != MembershipOrderType.MANUAL_GRANT
                    or existing_order.plan_id != plan.id
                ):
                    raise MembershipConflictError("该幂等请求键已用于其他会员订单。")
                existing_period = repository.get_period_by_order(self._session, existing_order.id)
                if existing_period is None:
                    raise MembershipUnavailableError
                result = MembershipGrantResult(
                    order_id=str(existing_order.id),
                    user_id=user.id,
                    email=normalized_email,
                    plan_name=plan.name,
                    starts_at=_as_utc(existing_period.starts_at),
                    expires_at=_as_utc(existing_period.expires_at),
                    already_applied=True,
                )
                self._session.commit()
            else:
                granted_at = _as_utc(self._clock())
                order = repository.create_manual_grant_order(
                    self._session,
                    user_id=user.id,
                    plan=plan,
                    request_id=str(request_id),
                    reason=normalized_reason,
                )
                latest_expiry = repository.latest_period_expiry(self._session, user.id)
                starts_at = granted_at
                if latest_expiry is not None:
                    starts_at = max(granted_at, _as_utc(latest_expiry))
                expires_at = starts_at + timedelta(days=plan.duration_days)
                repository.create_period(
                    self._session,
                    order_id=order.id,
                    user_id=user.id,
                    starts_at=starts_at,
                    expires_at=expires_at,
                )
                order_id = str(order.id)
                user_id = user.id
                self._session.commit()
                result = MembershipGrantResult(
                    order_id=order_id,
                    user_id=user_id,
                    email=normalized_email,
                    plan_name=plan.name,
                    starts_at=starts_at,
                    expires_at=expires_at,
                    already_applied=False,
                )
        except (MembershipConflictError, MembershipNotFoundError, MembershipUnavailableError):
            self._session.rollback()
            raise
        except SQLAlchemyError:
            self._session.rollback()
            logger.exception("membership_manual_grant_failed email=%s", normalized_email)
            raise MembershipUnavailableError from None

        self._invalidate_access_cache(result.user_id)
        return result

    def get_order(self, *, user_id: int, order_id: int) -> MembershipOrderResponse:
        """读取当前用户自己的会员订单详情。"""

        try:
            row = repository.get_order_with_plan(self._session, order_id, user_id)
            if row is None:
                raise MembershipNotFoundError("会员订单不存在。")
            return _order_response(*row)
        except MembershipNotFoundError:
            raise
        except SQLAlchemyError:
            logger.exception("membership_order_read_failed user_id=%s", user_id)
            raise MembershipUnavailableError from None

    def list_orders(
        self, *, user_id: int, page: int, page_size: int
    ) -> MembershipOrderPageResponse:
        """读取当前用户的会员订单分页列表。"""

        try:
            items = repository.list_orders(
                self._session,
                user_id,
                limit=page_size,
                offset=(page - 1) * page_size,
            )
            total = repository.count_orders(self._session, user_id)
            return MembershipOrderPageResponse(
                items=[_order_response(order, plan) for order, plan in items],
                total=total,
                page=page,
                page_size=page_size,
            )
        except SQLAlchemyError:
            logger.exception("membership_order_list_failed user_id=%s", user_id)
            raise MembershipUnavailableError from None

    def get_overview(self, *, user_id: int) -> MembershipOverviewResponse:
        """按服务器 UTC 时间读取当前、未来和最近过期会员期限。"""

        try:
            now = _as_utc(self._clock())
            rows = repository.list_periods(self._session, user_id)
            active: MembershipPeriodResponse | None = None
            upcoming: list[MembershipPeriodResponse] = []
            expired: list[tuple[Membership, MembershipOrder, MembershipPlan]] = []
            for membership, order, plan in rows:
                starts_at = _as_utc(membership.starts_at)
                expires_at = _as_utc(membership.expires_at)
                if starts_at <= now < expires_at:
                    active = _period_response(membership, order, plan)
                elif starts_at > now:
                    upcoming.append(_period_response(membership, order, plan))
                else:
                    expired.append((membership, order, plan))

            latest_expired = None
            if expired:
                latest_expired_row = max(expired, key=lambda row: _as_utc(row[0].expires_at))
                latest_expired = _period_response(*latest_expired_row)
            return MembershipOverviewResponse(
                active_period=active,
                upcoming_periods=upcoming,
                latest_expired_period=latest_expired,
            )
        except SQLAlchemyError:
            logger.exception("membership_overview_read_failed user_id=%s", user_id)
            raise MembershipUnavailableError from None

    def get_payment_context(self, *, user_id: int, order_id: int) -> PaymentOrderContext:
        """向支付模块提供订单所有权和服务器端金额快照。"""

        try:
            row = repository.get_order_with_plan(self._session, order_id, user_id)
            if row is None:
                raise MembershipNotFoundError("会员订单不存在。")
            order, plan = row
            return PaymentOrderContext(
                order_id=order.id,
                user_id=order.user_id,
                plan_id=order.plan_id,
                plan_name=plan.name,
                amount=order.amount,
                duration_days=order.duration_days,
                status=order.status,
                stripe_session_id=order.stripe_session_id,
            )
        except MembershipNotFoundError:
            raise
        except SQLAlchemyError:
            logger.exception("membership_payment_context_failed user_id=%s", user_id)
            raise MembershipUnavailableError from None

    def attach_checkout_session(self, *, user_id: int, order_id: int, session_id: str) -> None:
        """记录 Stripe Session ID，支持 Session 创建和 Webhook 的并发竞态。

        Step 1: 锁定本人订单，拒绝绑定到其他订单的 Session。
        Step 2: 相同 Session 重试幂等通过；空字段只允许绑定一次。
        Step 3: 提交 Session 关联，不保存 Checkout URL。
        """

        try:
            order = repository.get_order(self._session, order_id, user_id=user_id, for_update=True)
            if order is None:
                raise MembershipNotFoundError("会员订单不存在。")
            if order.stripe_session_id == session_id:
                self._session.commit()
                return
            if order.stripe_session_id is not None:
                raise MembershipConflictError("订单已绑定其他支付会话。")
            if order.status != MembershipOrderStatus.PENDING:
                raise MembershipConflictError("当前订单状态不能创建支付会话。")
            repository.set_checkout_session(order, session_id)
            self._session.commit()
        except (MembershipConflictError, MembershipNotFoundError):
            self._session.rollback()
            raise
        except SQLAlchemyError:
            self._session.rollback()
            logger.exception("membership_checkout_session_bind_failed order_id=%s", order_id)
            raise MembershipUnavailableError from None

    def mark_checkout_session_expired(
        self, *, user_id: int, order_id: int, session_id: str
    ) -> None:
        """在 Stripe 确认 Session 已过期时同步结束本地待支付订单。"""

        try:
            order = repository.get_order(self._session, order_id, user_id=user_id, for_update=True)
            if order is None:
                raise MembershipNotFoundError("会员订单不存在。")
            if order.stripe_session_id != session_id:
                raise MembershipConflictError("支付会话与会员订单不匹配。")
            if order.status == MembershipOrderStatus.PENDING:
                repository.mark_order_status(order, MembershipOrderStatus.EXPIRED)
            self._session.commit()
        except (MembershipConflictError, MembershipNotFoundError):
            self._session.rollback()
            raise
        except SQLAlchemyError:
            self._session.rollback()
            logger.exception("membership_checkout_expiry_update_failed order_id=%s", order_id)
            raise MembershipUnavailableError from None

    def apply_verified_payment_event(self, event: VerifiedPaymentEvent) -> bool:
        """根据已验签的标准支付事件更新订单并原子化发放会员期限。

        Step 1: 校验 Sandbox、Checkout 模式、订单引用、金额、币种和 Session 关联。
        Step 2: 锁定订单与用户行，重复成功事件只确认已有期限，不重复发放。
        Step 3: 将订单状态和按最大到期时间排期的会员期限放入同一事务提交。
        """

        order_id = self._referenced_order_id(event)
        if order_id is None:
            logger.warning("membership_payment_event_missing_order event_id=%s", event.event_id)
            return False

        try:
            order = repository.get_order(self._session, order_id, for_update=True)
            if order is None:
                logger.warning(
                    "membership_payment_event_order_not_found event_id=%s order_id=%s",
                    event.event_id,
                    order_id,
                )
                return False
            if not self._payment_event_matches_order(event, order):
                logger.warning(
                    "membership_payment_event_reconciliation_failed event_id=%s order_id=%s",
                    event.event_id,
                    order_id,
                )
                self._session.rollback()
                return False
            if event.outcome in {PaymentEventOutcome.FAILED, PaymentEventOutcome.EXPIRED}:
                if event.is_payment_settled:
                    self._session.rollback()
                    return False
                if event.outcome == PaymentEventOutcome.EXPIRED and not event.session_has_expired:
                    self._session.rollback()
                    return False

            if order.stripe_session_id is None:
                # Stripe 可能在 Session ID 落库前送达 Webhook；验签且元数据完全匹配时补绑。
                repository.set_checkout_session(order, event.session_id)

            if event.outcome == PaymentEventOutcome.PENDING:
                self._session.commit()
                return True
            if event.outcome == PaymentEventOutcome.PAID:
                if not event.is_payment_settled:
                    self._session.rollback()
                    return False
                if order.status == MembershipOrderStatus.PAID:
                    existing_period = repository.get_period_by_order(self._session, order.id)
                    if existing_period is None:
                        raise MembershipUnavailableError
                    user_id = order.user_id
                    self._session.commit()
                    self._invalidate_access_cache(user_id)
                    return True

                confirmed_at = _as_utc(self._clock())
                if repository.get_period_by_order(self._session, order.id) is None:
                    if repository.lock_user(self._session, order.user_id) is None:
                        raise MembershipUnavailableError
                    latest_expiry = repository.latest_period_expiry(self._session, order.user_id)
                    starts_at = confirmed_at
                    if latest_expiry is not None:
                        starts_at = max(confirmed_at, _as_utc(latest_expiry))
                    expires_at = starts_at + timedelta(days=order.duration_days)
                    repository.create_period(
                        self._session,
                        order_id=order.id,
                        user_id=order.user_id,
                        starts_at=starts_at,
                        expires_at=expires_at,
                    )
                repository.mark_order_status(
                    order, MembershipOrderStatus.PAID, paid_at=confirmed_at
                )
            elif event.outcome == PaymentEventOutcome.FAILED:
                if order.status == MembershipOrderStatus.PENDING:
                    repository.mark_order_status(order, MembershipOrderStatus.FAILED)
            elif event.outcome == PaymentEventOutcome.EXPIRED:
                if order.status == MembershipOrderStatus.PENDING:
                    repository.mark_order_status(order, MembershipOrderStatus.EXPIRED)

            paid_user_id = order.user_id if event.outcome == PaymentEventOutcome.PAID else None
            self._session.commit()
            if paid_user_id is not None:
                self._invalidate_access_cache(paid_user_id)
            return True
        except MembershipUnavailableError:
            self._session.rollback()
            raise
        except SQLAlchemyError:
            self._session.rollback()
            logger.exception(
                "membership_payment_event_apply_failed event_id=%s order_id=%s",
                event.event_id,
                order_id,
            )
            raise MembershipUnavailableError from None

    def _invalidate_access_cache(self, user_id: int) -> None:
        """会员期限提交成功后清除该用户的准入缓存。"""

        if self._access_cache is None:
            return
        try:
            self._access_cache.invalidate(user_id)
        except RedisError:
            logger.exception("membership_access_cache_invalidation_failed user_id=%s", user_id)
            raise MembershipUnavailableError from None

    @staticmethod
    def _referenced_order_id(event: VerifiedPaymentEvent) -> int | None:
        """从支付引用中解析正数会员订单 ID。"""

        if not event.order_reference or not event.client_reference_id:
            return None
        if event.order_reference != event.client_reference_id:
            return None
        try:
            order_id = int(event.order_reference)
        except ValueError:
            return None
        return order_id if order_id > 0 else None

    @staticmethod
    def _payment_event_matches_order(
        event: VerifiedPaymentEvent,
        order: MembershipOrder,
    ) -> bool:
        """核对验签事件中的订单、用户、套餐、Session、币种和金额快照。"""

        expected_amount = int((order.amount * CENT_AMOUNT_MULTIPLIER).to_integral_exact())
        session_matches = order.stripe_session_id in {None, event.session_id}
        return all(
            (
                order.order_type == MembershipOrderType.PURCHASE,
                not event.is_live,
                event.mode == CHECKOUT_MODE,
                event.order_reference == str(order.id),
                event.client_reference_id == str(order.id),
                event.metadata_user_id == str(order.user_id),
                event.metadata_plan_id == str(order.plan_id),
                session_matches,
                bool(event.session_id),
                event.currency == MEMBERSHIP_CURRENCY,
                event.amount_total == expected_amount,
            )
        )

    @staticmethod
    def _created_order_response(order: MembershipOrder) -> CreateMembershipOrderResponse:
        """将新建或幂等复用的订单转换为创建响应。"""

        return CreateMembershipOrderResponse(
            order_id=str(order.id),
            status=MembershipOrderStatus(order.status),
            amount=_amount_text(order.amount),
            order_type=MembershipOrderType(order.order_type),
            duration_days=order.duration_days,
            created_at=order.created_at,
        )
