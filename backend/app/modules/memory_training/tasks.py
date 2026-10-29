"""定义独立 Celery 视觉出题任务，并将结果写入短期 Redis 会话。"""

import asyncio
import logging

from app.core.celery_app import celery_app
from app.core.config import get_settings
from app.infrastructure.llm import OpenAICompatibleChatModelProvider
from app.infrastructure.redis.client import create_redis_client
from app.modules.memory_training.constants import (
    GENERATION_ERROR_FAILED,
    MAX_GENERATION_RETRIES,
    QUESTION_COUNT,
    QUESTION_GENERATION_RETRY_DELAY_SECONDS,
    QUESTION_TASK_NAME,
    SESSION_GENERATION_FAILED,
)
from app.modules.memory_training.errors import MemoryTrainingUnavailableError
from app.modules.memory_training.question_generator import MemoryTrainingQuestionGenerator
from app.modules.memory_training.state_store import MemoryTrainingStateStore

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name=QUESTION_TASK_NAME, max_retries=MAX_GENERATION_RETRIES)
def generate_training_questions(task, session_id: str) -> str:
    """读取会话图片链接，使用当前模型生成并保存校验后的题目。"""

    settings = get_settings()
    redis_client = create_redis_client()
    state_store = MemoryTrainingStateStore(redis_client)
    try:
        state = state_store.get_any(session_id)
        if state is None or state.questions or state.generation_error_code:
            return "ignored"
        if state.state not in {"observing", "waiting_questions"}:
            return "ignored"

        model = OpenAICompatibleChatModelProvider(
            settings,
            api_key=settings.aliyun_bailian_api_key,
            base_url=settings.aliyun_bailian_base_url,
            model_name=settings.aliyun_bailian_model,
            provider_name="阿里云百炼",
        ).create_chat_model()
        generator = MemoryTrainingQuestionGenerator(model)
        questions = asyncio.run(generator.generate(state.image_url))
        if len(questions) != QUESTION_COUNT:
            raise MemoryTrainingUnavailableError("模型未返回完整题目。")
        state_store.save_questions(session_id, questions)
        return "completed"
    except Exception as error:
        logger.exception("memory_training_question_generation_failed session_id=%s", session_id)
        if task.request.retries < MAX_GENERATION_RETRIES:
            raise task.retry(
                exc=error,
                countdown=QUESTION_GENERATION_RETRY_DELAY_SECONDS,
            ) from error
        state_store.mark_generation_failed(session_id, GENERATION_ERROR_FAILED)
        return SESSION_GENERATION_FAILED
    finally:
        redis_client.close()
