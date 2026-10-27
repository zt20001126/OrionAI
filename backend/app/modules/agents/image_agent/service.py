"""管理任务结果持久化和登录用户的图片读取。"""

import logging
from collections.abc import Callable
from typing import Any

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings
from app.infrastructure.database.session import SessionLocal
from app.infrastructure.storage.aliyun_oss import AliyunOSSObjectStorage
from app.infrastructure.storage.object_storage import ObjectStorageError
from app.modules.agents.image_agent import repository

logger = logging.getLogger(__name__)


class ImageTaskResultStore:
    """给图片工具使用独立短事务，避免跨越对话请求的 Session。"""

    def __init__(self, session_factory: sessionmaker[Session] = SessionLocal) -> None:
        self._session_factory = session_factory

    def create_running(
        self,
        *,
        task_result_id: int,
        user_id: int,
        conversation_id: int,
        input_data: dict[str, Any],
    ) -> None:
        with self._session_factory() as session:
            try:
                repository.create_task_result(
                    session,
                    task_result_id=task_result_id,
                    user_id=user_id,
                    conversation_id=conversation_id,
                    input_data=input_data,
                )
                session.commit()
            except SQLAlchemyError:
                session.rollback()
                raise

    def set_status(
        self,
        task_result_id: int,
        *,
        status: str,
        result_data: dict[str, Any] | None = None,
    ) -> None:
        with self._session_factory() as session:
            try:
                repository.set_task_result_status(
                    session, task_result_id, status=status, result_data=result_data
                )
                session.commit()
            except SQLAlchemyError:
                session.rollback()
                raise


class ImageTaskResultService:
    """校验所有权、任务状态后才读取私有 OSS 图片。"""

    def __init__(
        self,
        *,
        session: Session,
        settings: Settings | None = None,
        storage_factory: Callable[[], AliyunOSSObjectStorage] | None = None,
    ) -> None:
        self._session = session
        self._settings = settings or get_settings()
        self._storage_factory = storage_factory or (lambda: AliyunOSSObjectStorage(self._settings))

    def get_image(self, user_id: int, task_result_id: int) -> tuple[bytes, str]:
        try:
            result = repository.get_user_task_result(self._session, user_id, task_result_id)
        except SQLAlchemyError:
            self._session.rollback()
            raise ImageResultUnavailableError from None
        if result is None or result.generation_status != "succeeded" or not result.result_data:
            raise ImageResultUnavailableError
        object_key = result.result_data.get("object_key")
        content_type = result.result_data.get("mime_type")
        if not isinstance(object_key, str) or content_type not in {"image/png", "image/jpeg"}:
            raise ImageResultUnavailableError
        try:
            stored = self._storage_factory().get_object(
                object_key, max_bytes=self._settings.image_result_max_bytes
            )
        except (ObjectStorageError, ValueError):
            logger.warning("image_result_storage_read_failed task_result_id=%s", task_result_id)
            raise ImageResultUnavailableError from None
        if stored.content_type and stored.content_type.split(";")[0].lower() != content_type:
            raise ImageResultUnavailableError
        return stored.data, content_type


class ImageResultUnavailableError(Exception):
    """结果不存在、不可访问或尚未生成完成。"""


def link_image_result_message(
    session: Session,
    task_result_id: int,
    message_id: int,
) -> None:
    """将成功助手消息和私有生图任务建立关联。"""
    repository.link_result_message(session, task_result_id, message_id)
