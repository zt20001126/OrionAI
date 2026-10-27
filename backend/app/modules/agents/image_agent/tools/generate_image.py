"""调用 TokenHub 并安全持久化生成的图片和任务状态。"""

import asyncio
import json
import logging
from collections.abc import Callable
from contextlib import suppress
from typing import Any

from langchain_core.tools import tool
from pydantic import BaseModel, ConfigDict, Field

from app.core.config import Settings
from app.infrastructure.storage.object_storage import ObjectStorageError
from app.modules.agents.image_agent.constants import IMAGE_AGENT_CODE
from app.modules.image_generation.providers.result_downloader import ImageResultDownloader
from app.modules.image_generation.providers.tokenhub_client import (
    TokenHubImageClient,
    TokenHubImageError,
)
from app.modules.image_generation.schemas import ImageGenerationOptions
from app.modules.image_generation.service import TaskResultStore

logger = logging.getLogger(__name__)


class GenerateImageToolInput(BaseModel):
    """由图节点构造的生图工具参数及服务端运行标识。"""

    model_config = ConfigDict(extra="forbid")

    task_result_id: str = Field(min_length=1, max_length=20, pattern=r"^[0-9]+$")
    user_id: int = Field(gt=0)
    conversation_id: int = Field(gt=0)
    prompt: str = Field(min_length=1, max_length=8_000)
    size: str | None = Field(default=None, max_length=16)
    generate_max_pixels: int | None = None
    seed: int | None = Field(default=None, ge=0, le=9_223_372_036_854_775_807)
    footnote: str | None = Field(default=None, max_length=16)
    use_search_tool: bool = False


def create_generate_image_tool(
    *,
    settings: Settings,
    client: TokenHubImageClient,
    downloader: ImageResultDownloader,
    task_store: TaskResultStore,
    storage_factory: Callable[[], Any],
):
    """构造捕获图片 Provider、任务仓储及私有 OSS 工厂的 LangChain 工具。"""

    @tool("generate_image", args_schema=GenerateImageToolInput)
    async def generate_image(
        task_result_id: str,
        user_id: int,
        conversation_id: int,
        prompt: str,
        size: str | None = None,
        generate_max_pixels: int | None = None,
        seed: int | None = None,
        footnote: str | None = None,
        use_search_tool: bool = False,
    ) -> str:
        """生成一张商品图片，并保存私有对象和任务记录。"""
        try:
            options = ImageGenerationOptions(
                size=size,
                generate_max_pixels=generate_max_pixels,
                seed=seed,
                footnote=footnote,
                use_search_tool=use_search_tool,
            ).validate_exclusivity()
            task_id = int(task_result_id)
            task_store.create_running(
                task_result_id=task_id,
                user_id=user_id,
                conversation_id=conversation_id,
                skill_code=IMAGE_AGENT_CODE,
            )
            provider_result = await client.generate(
                prompt=prompt,
                options=options,
                session_id=str(conversation_id),
            )
            image_data, mime_type = await downloader.download(provider_result.image_url)
            extension = "png" if mime_type == "image/png" else "jpg"
            object_key = f"images/{user_id}/{conversation_id}/{task_id}.{extension}"
            storage = await asyncio.to_thread(storage_factory)
            stored = await asyncio.to_thread(
                storage.put_object,
                object_key,
                image_data,
                content_type=mime_type,
                metadata={"task-result-id": str(task_id)},
            )
            result_data = {
                "object_key": stored.key,
                "mime_type": mime_type,
                "file_size": len(image_data),
                "width": provider_result.width,
                "height": provider_result.height,
                "provider_model": provider_result.provider_model,
                "request_id": provider_result.request_id,
                "usage_total_tokens": provider_result.metadata.get("usage_total_tokens"),
            }
            task_store.set_status(task_id, status="succeeded", result_data=result_data)
            return json.dumps(
                {
                    "success": True,
                    "task_result_id": str(task_id),
                    "summary": "图片已生成并保存到本次会话。",
                },
                ensure_ascii=False,
            )
        except TokenHubImageError as error:
            logger.warning(
                "image_generation_failed task_result_id=%s code=%s request_id=%s",
                task_result_id,
                error.code,
                error.request_id,
            )
            _mark_failed(task_store, task_result_id)
            return _failure(error.public_message)
        except (ObjectStorageError, ValueError) as error:
            logger.warning(
                "image_generation_storage_or_input_failed task_result_id=%s error_type=%s",
                task_result_id,
                type(error).__name__,
            )
            _mark_failed(task_store, task_result_id)
            return _failure("图片暂时无法保存，请稍后重试。")
        except Exception as error:
            logger.warning(
                "image_generation_failed task_result_id=%s error_type=%s",
                task_result_id,
                type(error).__name__,
            )
            _mark_failed(task_store, task_result_id)
            return _failure("图片生成暂时失败，请稍后重试。")

    return generate_image


def _mark_failed(task_store: TaskResultStore, task_result_id: str) -> None:
    with suppress(Exception):
        task_store.set_status(int(task_result_id), status="failed")


def _failure(message: str) -> str:
    return json.dumps({"success": False, "summary": message}, ensure_ascii=False)
