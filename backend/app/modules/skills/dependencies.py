"""提供 skills Router 所需的认证、数据库和 Service 依赖。"""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.infrastructure.database.session import get_db_session
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.skills.service import SkillsService


def get_skills_service(session: Annotated[Session, Depends(get_db_session)]) -> SkillsService:
    """构造每请求的技能 Service。"""

    return SkillsService(session)


CurrentUser = Annotated[User, Depends(get_current_user)]
SkillsServiceDependency = Annotated[SkillsService, Depends(get_skills_service)]
