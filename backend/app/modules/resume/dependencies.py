"""构造请求作用域的简历业务服务。"""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.infrastructure.database.session import get_db_session
from app.infrastructure.storage.aliyun_oss import AliyunOSSObjectStorage
from app.modules.resume.pdf_renderer import PlaywrightResumePdfRenderer
from app.modules.resume.photo_storage import (
    AliyunResumePhotoStorage,
    ResumePhotoStorage,
    UnavailableResumePhotoStorage,
)
from app.modules.resume.service import ResumeApplicationService


def get_resume_photo_storage(settings: Settings) -> ResumePhotoStorage:
    if not settings.aliyun_oss_configured:
        return UnavailableResumePhotoStorage()
    return AliyunResumePhotoStorage(AliyunOSSObjectStorage(settings))


def get_resume_service(
    session: Annotated[Session, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ResumeApplicationService:
    return ResumeApplicationService(
        session,
        photo_storage=get_resume_photo_storage(settings),
        pdf_renderer=PlaywrightResumePdfRenderer(),
    )


ResumeServiceDependency = Annotated[
    ResumeApplicationService,
    Depends(get_resume_service),
]
