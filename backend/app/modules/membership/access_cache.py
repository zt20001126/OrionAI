"""封装会员准入状态的 Redis 缓存读写与失效。"""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from math import ceil

from redis import Redis

from app.modules.membership.constants import (
    MEMBERSHIP_ACCESS_CACHE_KEY_PREFIX,
    MEMBERSHIP_ACCESS_CACHE_TTL_SECONDS,
    NONMEMBER_ACCESS_CACHE_TTL_SECONDS,
)


@dataclass(frozen=True)
class MembershipAccessCacheEntry:
    """Redis 中缓存的会员资格和下一次状态变化边界。"""

    is_member: bool
    valid_until: datetime | None


class MembershipAccessCache:
    """按用户 ID 缓存会员准入结果，并让缓存不跨过期限状态变化。"""

    def __init__(self, redis_client: Redis) -> None:
        self._redis = redis_client

    def get(self, user_id: int, *, now: datetime) -> MembershipAccessCacheEntry | None:
        """读取尚未过期的会员准入缓存；无效数据按缓存未命中处理。"""

        raw_value = self._redis.get(self._key(user_id))
        if raw_value is None:
            return None

        try:
            payload = json.loads(raw_value)
            is_member = payload["is_member"]
            valid_until_value = payload["valid_until"]
            if not isinstance(is_member, bool):
                raise ValueError("会员缓存状态格式无效。")
            if valid_until_value is not None and not isinstance(valid_until_value, str):
                raise ValueError("会员缓存边界格式无效。")
            valid_until = (
                _as_utc(datetime.fromisoformat(valid_until_value))
                if valid_until_value is not None
                else None
            )
        except (AttributeError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            self.invalidate(user_id)
            return None

        if valid_until is not None and valid_until <= _as_utc(now):
            self.invalidate(user_id)
            return None
        return MembershipAccessCacheEntry(is_member=is_member, valid_until=valid_until)

    def set(
        self,
        user_id: int,
        *,
        is_member: bool,
        valid_until: datetime | None,
        now: datetime,
    ) -> None:
        """写入资格结果，并把 TTL 截断在期限开始或到期边界。"""

        cache_ttl = (
            MEMBERSHIP_ACCESS_CACHE_TTL_SECONDS if is_member else NONMEMBER_ACCESS_CACHE_TTL_SECONDS
        )
        utc_now = _as_utc(now)
        utc_valid_until = _as_utc(valid_until) if valid_until is not None else None
        if utc_valid_until is not None:
            remaining_seconds = ceil((utc_valid_until - utc_now).total_seconds())
            if remaining_seconds <= 0:
                return
            cache_ttl = min(cache_ttl, remaining_seconds)

        payload = json.dumps(
            {
                "is_member": is_member,
                "valid_until": utc_valid_until.isoformat() if utc_valid_until else None,
            },
            separators=(",", ":"),
        )
        self._redis.set(self._key(user_id), payload, ex=cache_ttl)

    def invalidate(self, user_id: int) -> None:
        """删除一个用户的会员准入缓存。"""

        self._redis.delete(self._key(user_id))

    @staticmethod
    def _key(user_id: int) -> str:
        """生成包含用户隔离信息的会员缓存键。"""

        return f"{MEMBERSHIP_ACCESS_CACHE_KEY_PREFIX}:{user_id}"


def _as_utc(value: datetime) -> datetime:
    """将数据库或缓存时间统一转换为 UTC。"""

    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
