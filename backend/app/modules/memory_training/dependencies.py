"""提供记忆训练 API 所需的认证、SQLAlchemy、Redis 和 Celery 依赖。"""

from typing import Annotated

from fastapi import Depends
from redis import Redis
from sqlalchemy.orm import Session

from app.core.celery_app import celery_app
from app.core.config import get_settings
from app.infrastructure.database.session import get_db_session
from app.infrastructure.redis.client import get_redis_client
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.memory_training.constants import QUESTION_TASK_NAME
from app.modules.memory_training.service import MemoryTrainingService


def get_memory_training_service(
    session: Annotated[Session, Depends(get_db_session)],
    redis_client: Annotated[Redis, Depends(get_redis_client)],
) -> MemoryTrainingService:
    """构造请求级 Service，并将题目生成投递到独立 Celery 队列。"""

    settings = get_settings()

    def dispatch_question_generation(session_id: str) -> None:
        celery_app.send_task(
            QUESTION_TASK_NAME,
            args=[session_id],
            queue=settings.memory_training_task_queue,
        )

    return MemoryTrainingService(
        session=session,
        redis_client=redis_client,
        dispatch_question_generation=dispatch_question_generation,
    )


CurrentUser = Annotated[User, Depends(get_current_user)]
MemoryTrainingServiceDependency = Annotated[
    MemoryTrainingService,
    Depends(get_memory_training_service),
]
