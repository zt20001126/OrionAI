"""提供反馈业务所需的 Redis 客户端、邮件配置和 Service。"""

from typing import Annotated

from fastapi import Depends
from redis import Redis

from app.core.config import Settings, get_settings
from app.infrastructure.redis.client import get_redis_client
from app.modules.feedback.service import FeedbackService


def get_feedback_service(
    redis_client: Annotated[Redis, Depends(get_redis_client)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> FeedbackService:
    """构造每请求使用的反馈 Service。"""

    return FeedbackService(redis_client, settings)


FeedbackServiceDependency = Annotated[FeedbackService, Depends(get_feedback_service)]
