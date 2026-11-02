"""提供会员 Router 所需的数据库和应用服务依赖。"""

from typing import Annotated

from fastapi import Depends
from redis import Redis
from sqlalchemy.orm import Session

from app.infrastructure.database.session import get_db_session
from app.infrastructure.redis.client import get_redis_client
from app.modules.auth.dependencies import CurrentUser
from app.modules.membership.access_cache import MembershipAccessCache
from app.modules.membership.access_service import MembershipAccessService
from app.modules.membership.service import MembershipService


def get_membership_access_cache(
    redis_client: Annotated[Redis, Depends(get_redis_client)],
) -> MembershipAccessCache:
    """构造请求范围的会员准入缓存适配器。"""

    return MembershipAccessCache(redis_client)


def get_membership_service(
    session: Annotated[Session, Depends(get_db_session)],
    cache: Annotated[MembershipAccessCache, Depends(get_membership_access_cache)],
) -> MembershipService:
    """构造当前请求范围内的会员应用服务。"""

    return MembershipService(session, access_cache=cache)


def get_membership_access_service(
    session: Annotated[Session, Depends(get_db_session)],
    cache: Annotated[MembershipAccessCache, Depends(get_membership_access_cache)],
) -> MembershipAccessService:
    """构造会员准入业务服务，供准入查询与受保护技能接口复用。"""

    return MembershipAccessService(session, cache)


def require_membership_access(
    user: CurrentUser,
    service: Annotated[MembershipAccessService, Depends(get_membership_access_service)],
) -> None:
    """拒绝没有有效会员资格的技能执行请求。"""

    service.require_member(user.id, is_guest=user.is_guest)


MembershipServiceDependency = Annotated[
    MembershipService,
    Depends(get_membership_service),
]
MembershipAccessServiceDependency = Annotated[
    MembershipAccessService,
    Depends(get_membership_access_service),
]
