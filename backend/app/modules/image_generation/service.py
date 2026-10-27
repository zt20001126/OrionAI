"""管理图片任务状态、结果关联及登录用户的私有图片读取。"""

import logging
from collections.abc import Callable
from typing import Any

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings
from app.infrastructure.database.session import SessionLocal
from app.infrastructure.storage.aliyun_oss import AliyunOSSObjectStorage
from app.infrastructure.storage.object_storage import ObjectStorageError
from app.modules.image_generation import repository

logger = logging.getLogger(__name__)


class TaskResultStore:
    """为技能任务结果提供独立短事务，避免跨越对话请求的 Session。"""

    def __init__(self, session_factory: sessionmaker[Session] = SessionLocal) -> None:
        self._session_factory = session_factory

    def create_running(
        self,
        *,
        task_result_id: int,
        user_id: int,
        conversation_id: int | None,
        skill_code: str,
    ) -> None:
        """创建运行中任务并提交短事务。

        Step 1: 创建独立数据库会话。
        Step 2: 委托 Repository 写入任务初始状态。
        Step 3: 提交事务；数据库失败时回滚并向调用方传播。
        """
        with self._session_factory() as session:
            try:
                repository.create_task_result(
                    session,
                    result_id=task_result_id,
                    user_id=user_id,
                    conversation_id=conversation_id,
                    skill_code=skill_code,
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
        """更新任务状态并提交短事务。

        Step 1: 创建独立数据库会话。
        Step 2: 委托 Repository 更新任务状态及结果元数据。
        Step 3: 提交事务；数据库失败时回滚并向调用方传播。
        """
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
    """校验所有权、任务状态和对象元数据后读取私有图片。"""

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
        """读取当前用户已成功生成的图片。

        Step 1: 按用户 ID 和任务 ID 查询任务，验证所有权及生成状态。
        Step 2: 校验对象键和 MIME 元数据后从私有 OSS 读取受大小限制的图片。
        Step 3: 核对对象返回的 MIME 类型并返回图片字节及类型。
        """
        try:
            result = repository.get_user_task_result(self._session, user_id, task_result_id)
        except SQLAlchemyError:
            self._session.rollback()
            raise ImageResultUnavailableError from None
        if result is None:
            raise ImageResultUnavailableError
        task_result_data = result.result
        if (
            not isinstance(task_result_data, dict)
            or task_result_data.get("generation_status") != "succeeded"
        ):
            raise ImageResultUnavailableError
        image_data = task_result_data.get("result_data")
        if not isinstance(image_data, dict):
            raise ImageResultUnavailableError
        object_key = image_data.get("object_key")
        content_type = image_data.get("mime_type")
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
