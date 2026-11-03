"""构造数字人请求范围服务并复用认证和数据库依赖。"""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.infrastructure.database.session import get_db_session
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.digital_human.service.service import DigitalHumanService


def get_digital_human_service(
    session: Annotated[Session, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> DigitalHumanService:
    """注入每请求数据库会话和语音配置。"""

    return DigitalHumanService(session=session, settings=settings)


DigitalHumanServiceDependency = Annotated[
    DigitalHumanService,
    Depends(get_digital_human_service),
]
CurrentUser = Annotated[User, Depends(get_current_user)]
