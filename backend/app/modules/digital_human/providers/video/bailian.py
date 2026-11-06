"""调用百炼视频生成任务接口并下载生成结果。"""

import httpx

from app.core.config import Settings
from app.modules.digital_human.constants import (
    DIGITAL_HUMAN_VIDEO_MAX_BYTES,
    DIGITAL_HUMAN_VIDEO_REQUEST_TIMEOUT_SECONDS,
)
from app.modules.digital_human.providers.base import get_bailian_request_context


class BailianVideoClient:
    """提交、查询百炼视频任务并下载 MP4。"""

    def __init__(self, settings: Settings) -> None:
        """保存百炼配置；调用方：数字人视频服务。"""
        self._origin, self._api_key = get_bailian_request_context(settings)
        self._model = settings.digital_human_video_model

    async def submit(self, prompt: str) -> str:
        """提交一次文生视频请求并返回百炼任务 ID；调用方：视频服务。"""
        async with httpx.AsyncClient(timeout=DIGITAL_HUMAN_VIDEO_REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.post(
                f"{self._origin}/api/v1/services/aigc/video-generation/video-synthesis",
                headers={"Authorization": f"Bearer {self._api_key}", "X-DashScope-Async": "enable"},
                json={"model": self._model, "input": {"prompt": prompt}},
            )
            response.raise_for_status()
            return str(response.json()["output"]["task_id"])

    async def get_task(self, task_id: str) -> dict:
        """查询指定百炼任务的状态和结果；调用方：视频服务。"""
        async with httpx.AsyncClient(timeout=DIGITAL_HUMAN_VIDEO_REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.get(
                f"{self._origin}/api/v1/tasks/{task_id}",
                headers={"Authorization": f"Bearer {self._api_key}"},
            )
            response.raise_for_status()
            return response.json()["output"]

    async def download(self, video_url: str) -> bytes:
        """下载大小受限的 MP4 数据；调用方：视频服务。"""
        async with httpx.AsyncClient(
            timeout=DIGITAL_HUMAN_VIDEO_REQUEST_TIMEOUT_SECONDS, follow_redirects=False
        ) as client:
            async with client.stream("GET", video_url) as response:
                response.raise_for_status()
                if response.headers.get("content-type", "").split(";")[0].lower() != "video/mp4":
                    raise ValueError("视频服务返回的文件类型无效。")
                chunks: list[bytes] = []
                total = 0
                async for chunk in response.aiter_bytes():
                    total += len(chunk)
                    if total > DIGITAL_HUMAN_VIDEO_MAX_BYTES:
                        raise ValueError("生成的视频超过系统大小限制。")
                    chunks.append(chunk)
        video = b"".join(chunks)
        if len(video) < 12 or video[4:8] != b"ftyp":
            raise ValueError("视频服务返回的文件内容无效。")
        return video
