"""定义会员订单状态和分页等业务常量。"""

from enum import StrEnum


class MembershipOrderStatus(StrEnum):
    """会员订单在本地业务中的持久化状态。"""

    PENDING = "pending"
    PAID = "paid"
    FAILED = "failed"
    EXPIRED = "expired"


DEFAULT_ORDER_PAGE_SIZE = 10
MAX_ORDER_PAGE_SIZE = 100
MIN_ORDER_PAGE = 1

MEMBERSHIP_ACCESS_CACHE_KEY_PREFIX = "orionai:membership:access"
MEMBERSHIP_ACCESS_CACHE_TTL_SECONDS = 300
NONMEMBER_ACCESS_CACHE_TTL_SECONDS = 30
