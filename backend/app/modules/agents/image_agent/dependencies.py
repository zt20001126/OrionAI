"""图片结果 Router 的数据库及认证依赖。"""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.infrastructure.database.session import get_db_session
from app.modules.agents.image_agent.service import ImageTaskResultService


def get_image_task_result_service(
    session: Annotated[Session, Depends(get_db_session)],
) -> ImageTaskResultService:
    return ImageTaskResultService(session=session)


ImageTaskResultServiceDependency = Annotated[
    ImageTaskResultService,
    Depends(get_image_task_result_service),
]
