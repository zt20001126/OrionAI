"""创建 OrionAI 共享体验账号，并为其发放 999 天体验会员。"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from redis.exceptions import RedisError  # noqa: E402
from sqlalchemy import select  # noqa: E402
from sqlalchemy.exc import SQLAlchemyError  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.infrastructure.database.session import SessionLocal  # noqa: E402
from app.infrastructure.redis.client import create_redis_client  # noqa: E402
from app.modules.auth.models import User  # noqa: E402
from app.modules.auth.service import hash_password, verify_password  # noqa: E402
from app.modules.membership.access_cache import MembershipAccessCache  # noqa: E402
from app.modules.membership.constants import (  # noqa: E402
    MembershipOrderStatus,
    MembershipOrderType,
)
from app.modules.membership.models import Membership, MembershipOrder, MembershipPlan  # noqa: E402
from app.modules.membership.repository import latest_period_expiry  # noqa: E402

DEMO_ACCOUNT = "admin@admin.com"
DEMO_PASSWORD = "admin"
DEMO_PLAN_NAME = "体验会员"
DEMO_MEMBERSHIP_DAYS = 999
DEMO_PLAN_PRICE = Decimal("999.00")
DEMO_GRANT_REASON = "OrionAI共享体验账号初始化"
DEMO_GRANT_REQUEST_ID = uuid5(
    NAMESPACE_URL,
    f"orionai:demo-membership:{DEMO_ACCOUNT}:v1",
)


def _build_parser() -> argparse.ArgumentParser:
    """定义预览模式，正式执行会写入数据库。"""

    parser = argparse.ArgumentParser(
        description="创建 admin@admin.com 共享体验账号并发放 999 天会员。"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="显示将执行的账号和会员配置，不连接或修改数据库。",
    )
    return parser


def _get_or_create_user(session: Session, now: datetime) -> User:
    """确保共享体验账号存在且密码为预设体验密码。"""

    user = session.scalar(select(User).where(User.account == DEMO_ACCOUNT).with_for_update())
    if user is None:
        user = User(
            account=DEMO_ACCOUNT,
            password_hash=hash_password(DEMO_PASSWORD),
            created_at=now,
        )
        session.add(user)
        session.flush()
        return user

    if user.is_guest:
        raise RuntimeError(f"{DEMO_ACCOUNT} 当前对应访客记录，无法作为体验账号使用。")

    if not verify_password(DEMO_PASSWORD, user.password_hash):
        user.password_hash = hash_password(DEMO_PASSWORD)
        session.flush()
    return user


def _get_or_create_demo_plan(session: Session) -> MembershipPlan:
    """确保体验会员套餐存在且不可从前台购买。"""

    plan = session.scalar(
        select(MembershipPlan).where(MembershipPlan.name == DEMO_PLAN_NAME).with_for_update()
    )
    if plan is None:
        plan = MembershipPlan(
            name=DEMO_PLAN_NAME,
            price=DEMO_PLAN_PRICE,
            duration_days=DEMO_MEMBERSHIP_DAYS,
            is_enabled=False,
        )
        session.add(plan)
        session.flush()
        return plan

    if plan.duration_days != DEMO_MEMBERSHIP_DAYS or plan.is_enabled:
        raise RuntimeError(
            f"数据库中的“{DEMO_PLAN_NAME}”套餐配置与脚本预期不符；请检查套餐天数及是否已关闭购买。"
        )
    return plan


def _get_existing_demo_period(
    session: Session,
    *,
    user_id: int,
    plan_id: int,
) -> Membership | None:
    """读取本脚本已经发放的期限，并检查幂等记录完整性。"""

    order = session.scalar(
        select(MembershipOrder)
        .where(
            MembershipOrder.user_id == user_id,
            MembershipOrder.request_id == str(DEMO_GRANT_REQUEST_ID),
        )
        .with_for_update()
    )
    if order is None:
        return None

    if (
        order.plan_id != plan_id
        or order.order_type != MembershipOrderType.MANUAL_GRANT
        or order.duration_days != DEMO_MEMBERSHIP_DAYS
        or order.status != MembershipOrderStatus.PAID
    ):
        raise RuntimeError("体验会员幂等订单与当前脚本配置不一致，已停止写入。")

    period = session.get(Membership, order.id)
    if period is None:
        raise RuntimeError("体验会员订单已存在但缺少期限记录，请先检查数据库。")
    return period


def _get_existing_active_demo_period(
    session: Session, user_id: int, now: datetime
) -> Membership | None:
    """复用账号上至少还剩 999 天的赠送期限，避免接管旧演示账号时重复加期。"""

    minimum_expiry = now + timedelta(days=DEMO_MEMBERSHIP_DAYS)
    statement = (
        select(Membership)
        .join(MembershipOrder, MembershipOrder.id == Membership.order_id)
        .where(
            Membership.user_id == user_id,
            Membership.expires_at >= minimum_expiry,
            MembershipOrder.order_type == MembershipOrderType.MANUAL_GRANT,
            MembershipOrder.duration_days == DEMO_MEMBERSHIP_DAYS,
        )
        .order_by(Membership.expires_at.desc())
        .limit(1)
    )
    return session.scalar(statement)


def _grant_demo_membership(
    session: Session,
    *,
    user: User,
    plan: MembershipPlan,
    now: datetime,
) -> tuple[Membership, bool]:
    """用唯一请求 ID 发放 999 天会员，重复运行时返回原期限。"""

    existing_period = _get_existing_demo_period(
        session,
        user_id=user.id,
        plan_id=plan.id,
    )
    if existing_period is not None:
        return existing_period, True

    existing_active_period = _get_existing_active_demo_period(session, user.id, now)
    if existing_active_period is not None:
        return existing_active_period, True

    latest_expiry = latest_period_expiry(session, user.id)
    if latest_expiry is not None:
        if latest_expiry.tzinfo is None:
            latest_expiry = latest_expiry.replace(tzinfo=UTC)
        else:
            latest_expiry = latest_expiry.astimezone(UTC)

    starts_at = max(now, latest_expiry) if latest_expiry is not None else now
    expires_at = starts_at + timedelta(days=DEMO_MEMBERSHIP_DAYS)
    order = MembershipOrder(
        user_id=user.id,
        plan_id=plan.id,
        amount=Decimal("0.00"),
        order_type=MembershipOrderType.MANUAL_GRANT,
        grant_reason=DEMO_GRANT_REASON,
        duration_days=DEMO_MEMBERSHIP_DAYS,
        request_id=str(DEMO_GRANT_REQUEST_ID),
        status=MembershipOrderStatus.PAID,
        paid_at=now,
    )
    session.add(order)
    session.flush()

    period = Membership(
        order_id=order.id,
        user_id=user.id,
        starts_at=starts_at,
        expires_at=expires_at,
    )
    session.add(period)
    session.flush()
    return period, False


def main() -> int:
    """按配置初始化体验账号和会员；支持安全重复执行。"""

    args = _build_parser().parse_args()
    print(f"体验账号：{DEMO_ACCOUNT}")
    print(f"体验密码：{DEMO_PASSWORD}")
    print(f"会员套餐：{DEMO_PLAN_NAME}（{DEMO_MEMBERSHIP_DAYS} 天，不可购买）")
    if args.dry_run:
        print("当前为预览模式，数据库未连接或修改。去掉 --dry-run 后执行初始化。")
        return 0

    now = datetime.now(UTC)
    session = SessionLocal()
    redis_client = None
    user_id: int | None = None
    membership_starts_at: datetime | None = None
    membership_expires_at: datetime | None = None
    already_applied = False
    try:
        user = _get_or_create_user(session, now)
        plan = _get_or_create_demo_plan(session)
        existing_period = _get_existing_active_demo_period(session, user.id, now)
        if existing_period is not None:
            period = existing_period
            already_applied = True
        else:
            period, already_applied = _grant_demo_membership(
                session,
                user=user,
                plan=plan,
                now=now,
            )
        user_id = user.id
        membership_starts_at = period.starts_at
        membership_expires_at = period.expires_at
        session.commit()
    except (SQLAlchemyError, RuntimeError, ValueError) as error:
        session.rollback()
        print(f"体验账号初始化失败：{error}", file=sys.stderr)
        return 1
    finally:
        session.close()

    if user_id is None or membership_starts_at is None or membership_expires_at is None:
        print("体验账号初始化未生成用户 ID 或会员期限。", file=sys.stderr)
        return 1

    try:
        redis_client = create_redis_client()
        MembershipAccessCache(redis_client).invalidate(user_id)
    except RedisError:
        print(
            "数据库已提交，但 Redis 会员缓存未能清理；检查 Redis 后可安全重跑脚本。",
            file=sys.stderr,
        )
        return 1
    finally:
        if redis_client is not None:
            redis_client.close()

    action = "会员期限已存在，未重复发放" if already_applied else "会员发放成功"
    print(f"用户 ID：{user_id}")
    print(action)
    print(f"会员开始时间：{membership_starts_at.isoformat()}")
    print(f"会员到期时间：{membership_expires_at.isoformat()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
