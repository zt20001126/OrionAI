"""提供用户资料 Router 所需的认证和业务 Service 依赖。"""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.infrastructure.database.session import get_db_session
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.users.service import UsersService


def get_users_service(
    session: Annotated[Session, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> UsersService:
    """构造每请求的用户资料 Service。"""

    return UsersService(session=session, settings=settings)


CurrentUser = Annotated[User, Depends(get_current_user)]
UsersServiceDependency = Annotated[UsersService, Depends(get_users_service)]
