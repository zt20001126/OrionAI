"""验证会员准入查询、Redis 缓存边界和依赖故障处理。"""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from redis.exceptions import RedisError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.infrastructure.database.base import Base
from app.modules.auth.models import User
from app.modules.membership import repository
from app.modules.membership.access_cache import MembershipAccessCache
from app.modules.membership.access_service import MembershipAccessService
from app.modules.membership.errors import MembershipRequiredError, MembershipUnavailableError
from app.modules.membership.models import Membership, MembershipOrder, MembershipPlan

NOW = datetime(2026, 11, 2, 12, tzinfo=UTC)


class FakeRedis:
    """以可观察调用的内存字典替代单元测试中的 Redis 网络连接。"""

    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.expirations: dict[str, int] = {}
        self.get_calls = 0
        self.set_calls = 0
        self.delete_calls = 0
        self.fail_get = False

    def get(self, key: str) -> str | None:
        self.get_calls += 1
        if self.fail_get:
            raise RedisError("redis unavailable")
        return self.values.get(key)

    def set(self, key: str, value: str, *, ex: int) -> bool:
        self.set_calls += 1
        self.values[key] = value
        self.expirations[key] = ex
        return True

    def delete(self, key: str) -> int:
        self.delete_calls += 1
        self.expirations.pop(key, None)
        return int(self.values.pop(key, None) is not None)


@pytest.fixture
def membership_data() -> Iterator[tuple[Session, User, FakeRedis]]:
    """构造隔离的 SQLite 会员表和一个已登录用户。"""

    engine = create_engine("sqlite+pysqlite:///:memory:")
    tables = [
        User.__table__,
        MembershipPlan.__table__,
        MembershipOrder.__table__,
        Membership.__table__,
    ]
    Base.metadata.create_all(engine, tables=tables)
    with Session(engine) as session:
        user = User(account="access@example.test", password_hash="test-hash", is_guest=False)
        plan = MembershipPlan(
            name="准入测试套餐",
            price=Decimal("9.90"),
            duration_days=30,
            is_enabled=True,
        )
        session.add_all([user, plan])
        session.flush()
        order = MembershipOrder(
            user_id=user.id,
            plan_id=plan.id,
            amount=Decimal("9.90"),
            duration_days=30,
            request_id=str(uuid4()),
            status="paid",
        )
        session.add(order)
        session.commit()
        session.refresh(user)
        yield session, user, FakeRedis()
    engine.dispose()


def _add_period(
    session: Session,
    user: User,
    *,
    starts_at: datetime,
    expires_at: datetime,
) -> None:
    """为测试用户新增一条会员有效期限。"""

    order = session.query(MembershipOrder).filter_by(user_id=user.id).one()
    session.add(
        Membership(
            order_id=order.id,
            user_id=user.id,
            starts_at=starts_at,
            expires_at=expires_at,
        )
    )
    session.commit()


def test_active_membership_uses_redis_on_every_check_and_queries_database_once(
    membership_data: tuple[Session, User, FakeRedis],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """有效会员第一次查库写缓存，后续检查仍读 Redis 但不再查库。"""

    session, user, redis_client = membership_data
    expires_at = NOW + timedelta(days=2)
    _add_period(session, user, starts_at=NOW - timedelta(days=1), expires_at=expires_at)
    original_query = repository.get_access_period
    query_calls = 0

    def count_queries(*args: object, **kwargs: object) -> tuple[datetime, datetime] | None:
        nonlocal query_calls
        query_calls += 1
        return original_query(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(repository, "get_access_period", count_queries)
    service = MembershipAccessService(
        session,
        MembershipAccessCache(redis_client),
        clock=lambda: NOW,
    )

    assert service.is_member(user.id)
    assert service.is_member(user.id)

    key = "orionai:membership:access:" + str(user.id)
    assert redis_client.get_calls == 2
    assert redis_client.set_calls == 1
    assert redis_client.expirations[key] == 300
    assert query_calls == 1


def test_future_membership_negative_cache_expires_at_start_boundary(
    membership_data: tuple[Session, User, FakeRedis],
) -> None:
    """负缓存不跨越未来期限开始时间，开始时可立即识别为会员。"""

    session, user, redis_client = membership_data
    starts_at = NOW + timedelta(seconds=10)
    _add_period(session, user, starts_at=starts_at, expires_at=starts_at + timedelta(days=30))
    current_time = [NOW]
    service = MembershipAccessService(
        session,
        MembershipAccessCache(redis_client),
        clock=lambda: current_time[0],
    )

    assert not service.is_member(user.id)
    key = "orionai:membership:access:" + str(user.id)
    assert redis_client.expirations[key] == 10

    current_time[0] = starts_at
    assert service.is_member(user.id)
    assert redis_client.get_calls == 2
    assert redis_client.set_calls == 2


def test_cache_hit_is_rechecked_after_redis_read_at_expiration_boundary(
    membership_data: tuple[Session, User, FakeRedis],
) -> None:
    """会员在 Redis 读取期间到期时，不能沿用读取前的时钟结果。"""

    session, user, redis_client = membership_data
    expires_at = NOW + timedelta(seconds=1)
    _add_period(session, user, starts_at=NOW - timedelta(days=1), expires_at=expires_at)
    cache = MembershipAccessCache(redis_client)
    cache.set(
        user.id,
        is_member=True,
        valid_until=expires_at,
        now=NOW,
    )
    clock_values = iter(
        [
            expires_at - timedelta(milliseconds=1),
            expires_at,
            expires_at,
        ]
    )
    service = MembershipAccessService(session, cache, clock=lambda: next(clock_values))

    assert not service.is_member(user.id)
    assert redis_client.delete_calls == 1
    assert redis_client.values["orionai:membership:access:" + str(user.id)]


def test_expired_membership_is_not_member(membership_data: tuple[Session, User, FakeRedis]) -> None:
    """会员期限到期边界不包含在有效区间内。"""

    session, user, redis_client = membership_data
    _add_period(
        session,
        user,
        starts_at=NOW - timedelta(days=30),
        expires_at=NOW,
    )
    service = MembershipAccessService(
        session,
        MembershipAccessCache(redis_client),
        clock=lambda: NOW,
    )

    assert not service.is_member(user.id)


def test_guest_is_not_member_without_redis_lookup(
    membership_data: tuple[Session, User, FakeRedis],
) -> None:
    """访客不具备会员资格，也不创建 Redis 会员缓存。"""

    session, user, redis_client = membership_data
    service = MembershipAccessService(session, MembershipAccessCache(redis_client))

    assert not service.is_member(user.id, is_guest=True)
    assert redis_client.get_calls == 0
    assert redis_client.set_calls == 0


def test_require_member_raises_business_error_for_nonmember(
    membership_data: tuple[Session, User, FakeRedis],
) -> None:
    """无有效期限时统一返回会员准入 403。"""

    session, user, redis_client = membership_data
    service = MembershipAccessService(
        session,
        MembershipAccessCache(redis_client),
        clock=lambda: NOW,
    )

    with pytest.raises(MembershipRequiredError):
        service.require_member(user.id)


def test_redis_failure_fails_closed(membership_data: tuple[Session, User, FakeRedis]) -> None:
    """Redis 不可用时不回退到数据库放行。"""

    session, user, redis_client = membership_data
    redis_client.fail_get = True
    service = MembershipAccessService(session, MembershipAccessCache(redis_client))

    with pytest.raises(MembershipUnavailableError):
        service.is_member(user.id)
