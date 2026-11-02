"""按当前会员套餐配置，为指定注册用户免费发放一个月度会员期限。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from redis.exceptions import RedisError  # noqa: E402
from sqlalchemy.exc import SQLAlchemyError  # noqa: E402

from app.infrastructure.database.session import SessionLocal  # noqa: E402
from app.infrastructure.redis.client import create_redis_client  # noqa: E402
from app.modules.membership.access_cache import MembershipAccessCache  # noqa: E402
from app.modules.membership.constants import (  # noqa: E402
    MAX_MEMBERSHIP_GRANT_REASON_LENGTH,
    MONTHLY_MEMBERSHIP_DURATION_DAYS,
    MONTHLY_MEMBERSHIP_PLAN_NAME,
)
from app.modules.membership.errors import MembershipError  # noqa: E402
from app.modules.membership.service import MembershipService  # noqa: E402

DEFAULT_TARGET_EMAIL = "424503256@qq.com"
DEFAULT_GRANT_REASON = "管理员手动赠送月度会员"
DEFAULT_GRANT_REFERENCE = "monthly-membership"


def _build_parser() -> argparse.ArgumentParser:
    """定义赠送目标、审计原因和显式写入开关。"""

    parser = argparse.ArgumentParser(description="向用户赠送一个月度会员期限。")
    parser.add_argument(
        "--email",
        default=DEFAULT_TARGET_EMAIL,
        help=f"目标用户邮箱，默认：{DEFAULT_TARGET_EMAIL}",
    )
    parser.add_argument(
        "--reason",
        default=DEFAULT_GRANT_REASON,
        help="记录在后台赠送订单中的原因。",
    )
    parser.add_argument(
        "--reference",
        default=DEFAULT_GRANT_REFERENCE,
        help=("本次赠送的唯一引用。同一邮箱和引用值重跑不会重复发放；再次赠送时请使用新的引用值。"),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="仅显示目标和套餐信息，不修改数据库。",
    )
    return parser


def main() -> int:
    """默认提交会员赠送事务；指定 --dry-run 时仅预览操作参数。"""

    args = _build_parser().parse_args()
    email = args.email.strip().lower()
    if not email:
        print("目标邮箱不能为空。", file=sys.stderr)
        return 2
    reason = args.reason.strip()
    reference = args.reference.strip()
    if not reason or len(reason) > MAX_MEMBERSHIP_GRANT_REASON_LENGTH:
        print("赠送原因不能为空且不能超过 500 个字符。", file=sys.stderr)
        return 2
    if not reference:
        print("操作引用不能为空。", file=sys.stderr)
        return 2

    print(f"目标用户：{email}")
    print(f"套餐：{MONTHLY_MEMBERSHIP_PLAN_NAME}（{MONTHLY_MEMBERSHIP_DURATION_DAYS} 天）")
    print(f"赠送原因：{reason}")
    if args.dry_run:
        print("当前为预览模式，数据库未修改。去掉 --dry-run 后执行发放。")
        return 0

    request_id = uuid5(
        NAMESPACE_URL,
        f"orionai:membership-grant:{email}:{reference}",
    )
    session = SessionLocal()
    redis_client = None
    try:
        redis_client = create_redis_client()
        service = MembershipService(session, access_cache=MembershipAccessCache(redis_client))
        result = service.grant_monthly_membership(
            email=email,
            reason=reason,
            request_id=request_id,
        )
    except MembershipError as error:
        session.rollback()
        print(f"会员发放未完成：{error.detail}", file=sys.stderr)
        print(
            "如果数据库已提交但 Redis 缓存失效失败，可使用相同邮箱和引用值安全重跑。",
            file=sys.stderr,
        )
        return 1
    except (SQLAlchemyError, RedisError):
        session.rollback()
        print(
            "会员发放未完成，请检查数据库和 Redis 连接；相同邮箱和引用值可安全重跑。",
            file=sys.stderr,
        )
        return 1
    finally:
        session.close()
        if redis_client is not None:
            redis_client.close()

    action = "已存在，未重复增加期限" if result.already_applied else "发放成功"
    print(f"{action}：订单 {result.order_id}")
    print(f"会员开始时间：{result.starts_at.isoformat()}")
    print(f"会员到期时间：{result.expires_at.isoformat()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
