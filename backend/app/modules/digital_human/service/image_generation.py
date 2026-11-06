"""完成数字人图片生成，并复用现有任务记录和私有 OSS。"""

import asyncio
from contextlib import suppress

from app.core.config import Settings
from app.infrastructure.database.snowflake import generate_snowflake_id
from app.infrastructure.storage.aliyun_oss import AliyunOSSObjectStorage
from app.modules.digital_human.constants import DIGITAL_HUMAN_IMAGE_TIMEOUT_SECONDS
from app.modules.digital_human.providers.image.image_generation import BailianImageClient
from app.modules.digital_human.providers.image.image_result_downloader import (
    BailianImageResultDownloader,
)
from app.modules.image_generation.service import TaskResultStore


async def generate_and_save_image(
    *,
    settings: Settings,
    user_id: int,
    conversation_id: int,
    prompt: str,
) -> str:
    """生成图片并保存任务和 OSS 对象；调用方：数字人生图工具。"""
    task_result_id = generate_snowflake_id()
    task_store = TaskResultStore()
    task_store.create_running(
        task_result_id=task_result_id,
        user_id=user_id,
        conversation_id=conversation_id,
        skill_code="digital_human",
    )
    try:
        image_url = await BailianImageClient(settings).generate(prompt)
        image_data, content_type = await BailianImageResultDownloader(
            timeout_seconds=DIGITAL_HUMAN_IMAGE_TIMEOUT_SECONDS,
            max_bytes=settings.image_result_max_bytes,
        ).download(image_url)
        extension = "png" if content_type == "image/png" else "jpg"
        object_key = f"images/{user_id}/{conversation_id}/{task_result_id}.{extension}"
        storage = await asyncio.to_thread(AliyunOSSObjectStorage, settings)
        stored = await asyncio.to_thread(
            storage.put_object,
            object_key,
            image_data,
            content_type=content_type,
            metadata={"task-result-id": str(task_result_id)},
        )
        task_store.set_status(
            task_result_id,
            status="succeeded",
            result_data={"object_key": stored.key},
        )
    except Exception:
        with suppress(Exception):
            task_store.set_status(task_result_id, status="failed")
        raise
    return str(task_result_id)
