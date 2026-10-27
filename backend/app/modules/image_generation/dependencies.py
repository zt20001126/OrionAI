"""提供图片任务结果 API 所需的数据库与 Service 依赖。"""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.infrastructure.database.session import get_db_session
from app.modules.image_generation.service import ImageTaskResultService


def get_image_task_result_service(
    session: Annotated[Session, Depends(get_db_session)],
) -> ImageTaskResultService:
    """用请求作用域数据库会话构造图片结果 Service。"""
    return ImageTaskResultService(session=session)


ImageTaskResultServiceDependency = Annotated[
    ImageTaskResultService,
    Depends(get_image_task_result_service),
]
