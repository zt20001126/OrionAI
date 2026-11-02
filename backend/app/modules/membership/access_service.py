"""执行会员准入判断，并在缓存未命中时读取现有会员期限。"""

import logging
from collections.abc import Callable
from datetime import UTC, datetime

from redis.exceptions import RedisError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.modules.membership import repository
from app.modules.membership.access_cache import MembershipAccessCache
from app.modules.membership.errors import MembershipRequiredError, MembershipUnavailableError

logger = logging.getLogger(__name__)


def utc_now() -> datetime:
    """返回可在准入测试中替换的 UTC 当前时间。"""

    return datetime.now(UTC)


class MembershipAccessService:
    """按当前用户身份核验会员，并统一拒绝无会员资格的技能操作。"""

    def __init__(
        self,
        session: Session,
        cache: MembershipAccessCache,
        *,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._session = session
        self._cache = cache
        self._clock = clock

    def is_member(self, user_id: int, *, is_guest: bool = False) -> bool:
        """判断用户是否在当前时刻拥有有效会员。

        Step 1: 访客直接判定为非会员，注册用户每次先读取 Redis。
        Step 2: 缓存未命中时读取当前或下一段会员期限。
        Step 3: 计算资格并写入不会跨过状态变化边界的缓存。
        """

        if is_guest:
            return False

        now = _as_utc(self._clock())
        try:
            cached_entry = self._cache.get(user_id, now=now)
        except RedisError:
            logger.exception("membership_access_cache_read_failed user_id=%s", user_id)
            raise MembershipUnavailableError from None
        if cached_entry is not None:
            now = _as_utc(self._clock())
            if cached_entry.valid_until is None or cached_entry.valid_until > now:
                return cached_entry.is_member
            try:
                self._cache.invalidate(user_id)
            except RedisError:
                logger.exception("membership_access_cache_invalidation_failed user_id=%s", user_id)
                raise MembershipUnavailableError from None

        try:
            period = repository.get_access_period(self._session, user_id, now=now)
        except SQLAlchemyError:
            self._session.rollback()
            logger.exception("membership_access_period_read_failed user_id=%s", user_id)
            raise MembershipUnavailableError from None

        now = _as_utc(self._clock())
        is_member = False
        valid_until: datetime | None = None
        if period is not None:
            starts_at, expires_at = (_as_utc(period[0]), _as_utc(period[1]))
            if starts_at <= now < expires_at:
                is_member = True
                valid_until = expires_at
            elif starts_at > now:
                valid_until = starts_at

        try:
            self._cache.set(
                user_id,
                is_member=is_member,
                valid_until=valid_until,
                now=now,
            )
        except RedisError:
            logger.exception("membership_access_cache_write_failed user_id=%s", user_id)
            raise MembershipUnavailableError from None
        return is_member

    def require_member(self, user_id: int, *, is_guest: bool = False) -> None:
        """要求当前用户具备有效会员资格，否则返回稳定的 403 业务错误。"""

        if not self.is_member(user_id, is_guest=is_guest):
            raise MembershipRequiredError


def _as_utc(value: datetime) -> datetime:
    """将数据库时间统一转换为 UTC；兼容 SQLite 的无时区测试值。"""

    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
