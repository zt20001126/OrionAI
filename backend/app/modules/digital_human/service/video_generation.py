"""编排视频生成、任务状态与私有 OSS 保存。"""

import asyncio
import logging
from contextlib import suppress

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.infrastructure.database.snowflake import generate_snowflake_id
from app.infrastructure.storage.aliyun_oss import AliyunOSSObjectStorage
from app.infrastructure.storage.object_storage import ObjectStorageError
from app.modules.digital_human.constants import (
    DIGITAL_HUMAN_VIDEO_MAX_BYTES,
    DIGITAL_HUMAN_VIDEO_MAX_WAIT_SECONDS,
    DIGITAL_HUMAN_VIDEO_POLL_SECONDS,
)
from app.modules.digital_human.providers.video.bailian import BailianVideoClient
from app.modules.image_generation import repository
from app.modules.image_generation.service import TaskResultStore

logger = logging.getLogger(__name__)


async def generate_and_save_video(
    *, settings: Settings, user_id: int, conversation_id: int, prompt: str
) -> str:
    """生成并保存视频；输入可信用户、会话和提示词，输出任务 ID；调用方：视频工具。"""
    task_id = generate_snowflake_id()
    store = TaskResultStore()
    store.create_running(
        task_result_id=task_id,
        user_id=user_id,
        conversation_id=conversation_id,
        skill_code="digital_human",
    )
    try:
        client = BailianVideoClient(settings)
        provider_task_id = await client.submit(prompt)
        logger.info(
            "digital_human_video_task_submitted task_result_id=%s provider_task_id=%s",
            task_id,
            provider_task_id,
        )
        store.set_status(
            task_id, status="running", result_data={"provider_task_id": provider_task_id}
        )
        async with asyncio.timeout(DIGITAL_HUMAN_VIDEO_MAX_WAIT_SECONDS):
            while True:
                task = await client.get_task(provider_task_id)
                if task["task_status"] == "SUCCEEDED":
                    break
                if task["task_status"] in {"FAILED", "CANCELED", "UNKNOWN"}:
                    raise ValueError("视频生成任务失败或已过期。")
                await asyncio.sleep(DIGITAL_HUMAN_VIDEO_POLL_SECONDS)
        video = await client.download(task["video_url"])
        storage = await asyncio.to_thread(AliyunOSSObjectStorage, settings)
        key = f"videos/{user_id}/{conversation_id}/{task_id}.mp4"
        stored = await asyncio.to_thread(
            storage.put_object,
            key,
            video,
            content_type="video/mp4",
            metadata={"task-result-id": str(task_id)},
        )
        store.set_status(
            task_id,
            status="succeeded",
            result_data={
                "provider_task_id": provider_task_id,
                "object_key": stored.key,
            },
        )
    except (Exception, asyncio.CancelledError):
        with suppress(Exception):
            store.set_status(task_id, status="failed")
        raise
    return str(task_id)


class VideoResultUnavailableError(Exception):
    """视频结果不存在、无权访问或暂不可用。"""


def get_user_video(session: Session, user_id: int, task_result_id: int) -> bytes:
    """读取用户本人已完成的视频；输入用户和任务 ID，输出 MP4；调用方：视频路由。"""
    task = repository.get_user_task_result(session, user_id, task_result_id)
    if task is None or task.result.get("generation_status") != "succeeded":
        raise VideoResultUnavailableError
    result = task.result.get("result_data", {})
    key = result.get("object_key")
    if not isinstance(key, str) or not key.startswith(f"videos/{user_id}/"):
        raise VideoResultUnavailableError
    try:
        stored = AliyunOSSObjectStorage(get_settings()).get_object(
            key, max_bytes=DIGITAL_HUMAN_VIDEO_MAX_BYTES
        )
    except (ObjectStorageError, ValueError):
        logger.warning("digital_human_video_read_failed task_result_id=%s", task_result_id)
        raise VideoResultUnavailableError from None
    if stored.content_type != "video/mp4":
        raise VideoResultUnavailableError
    return stored.data
