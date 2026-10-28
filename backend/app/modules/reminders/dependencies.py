"""提供提醒 API 所需的认证、数据库会话和 Service 依赖。"""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.infrastructure.database.session import get_db_session
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.reminders.service import ReminderService


def get_reminder_service(
    session: Annotated[Session, Depends(get_db_session)],
) -> ReminderService:
    """为一个 API 请求创建使用该请求数据库会话的提醒 Service。"""

    return ReminderService(session)


CurrentUser = Annotated[User, Depends(get_current_user)]
ReminderServiceDependency = Annotated[
    ReminderService,
    Depends(get_reminder_service),
]
