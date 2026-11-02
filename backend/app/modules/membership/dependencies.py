"""提供会员 Router 所需的数据库和应用服务依赖。"""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.infrastructure.database.session import get_db_session
from app.modules.membership.service import MembershipService


def get_membership_service(
    session: Annotated[Session, Depends(get_db_session)],
) -> MembershipService:
    """构造当前请求范围内的会员应用服务。"""

    return MembershipService(session)


MembershipServiceDependency = Annotated[
    MembershipService,
    Depends(get_membership_service),
]
