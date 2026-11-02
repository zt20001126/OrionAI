"""定义会员订单状态和分页等业务常量。"""

from enum import StrEnum


class MembershipOrderStatus(StrEnum):
    """会员订单在本地业务中的持久化状态。"""

    PENDING = "pending"
    PAID = "paid"
    FAILED = "failed"
    EXPIRED = "expired"


class MembershipOrderType(StrEnum):
    """区分正常付费订单和管理员赠送订单。"""

    PURCHASE = "purchase"
    MANUAL_GRANT = "manual_grant"


DEFAULT_ORDER_PAGE_SIZE = 10
MAX_ORDER_PAGE_SIZE = 100
MIN_ORDER_PAGE = 1

MEMBERSHIP_ACCESS_CACHE_KEY_PREFIX = "orionai:membership:access"
MEMBERSHIP_ACCESS_CACHE_TTL_SECONDS = 300
NONMEMBER_ACCESS_CACHE_TTL_SECONDS = 30
MONTHLY_MEMBERSHIP_PLAN_NAME = "月度会员"
MONTHLY_MEMBERSHIP_DURATION_DAYS = 30
MAX_MEMBERSHIP_GRANT_REASON_LENGTH = 500
