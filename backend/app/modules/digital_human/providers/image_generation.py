"""通过阿里云百炼 OpenAI 兼容接口生成数字人图片。"""

import httpx

from app.core.config import Settings
from app.modules.digital_human.constants import DIGITAL_HUMAN_IMAGE_TIMEOUT_SECONDS
from app.modules.digital_human.providers.base import get_bailian_request_context
from app.modules.digital_human.providers.errors import DigitalHumanProviderError


class DigitalHumanImageProviderError(Exception):
    """携带可安全展示提示的数字人生图异常。"""

    def __init__(self, code: str, public_message: str) -> None:
        """保存稳定错误码和对用户安全的提示。"""
        super().__init__(public_message)
        self.code = code
        self.public_message = public_message


class BailianImageClient:
    """调用百炼图片生成 API 并返回短期图片地址。"""

    def __init__(self, settings: Settings) -> None:
        """保存数字人模型和百炼连接配置。"""
        self._settings = settings

    async def generate(self, prompt: str) -> str:
        """提交提示词并返回百炼临时图片地址；调用方负责下载和持久化。"""
        try:
            _, api_key = get_bailian_request_context(self._settings)
        except DigitalHumanProviderError as error:
            raise DigitalHumanImageProviderError(
                "BAILIAN_IMAGE_NOT_CONFIGURED", "阿里云百炼图片生成服务尚未正确配置。"
            ) from error
        base_url = self._settings.aliyun_bailian_base_url.strip().rstrip("/")
        try:
            async with httpx.AsyncClient(timeout=DIGITAL_HUMAN_IMAGE_TIMEOUT_SECONDS) as client:
                response = await client.post(
                    f"{base_url}/images/generations",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={
                        "model": self._settings.digital_human_image_model,
                        "prompt": prompt,
                        "n": 1,
                    },
                )
        except httpx.TimeoutException:
            raise DigitalHumanImageProviderError(
                "BAILIAN_IMAGE_TIMEOUT", "图片生成服务响应超时，请稍后重试。"
            ) from None
        except httpx.HTTPError:
            raise DigitalHumanImageProviderError(
                "BAILIAN_IMAGE_CONNECTION_FAILED", "暂时无法连接图片生成服务，请稍后重试。"
            ) from None

        if response.status_code == 401:
            raise DigitalHumanImageProviderError(
                "BAILIAN_IMAGE_AUTH_FAILED", "图片生成服务鉴权失败，请联系管理员。"
            )
        if response.status_code == 429:
            raise DigitalHumanImageProviderError(
                "BAILIAN_IMAGE_RATE_LIMITED", "图片生成请求较多，请稍后重试。"
            )
        if response.status_code >= 500:
            raise DigitalHumanImageProviderError(
                "BAILIAN_IMAGE_UNAVAILABLE", "图片生成服务暂时不可用，请稍后重试。"
            )
        if response.is_error:
            raise DigitalHumanImageProviderError(
                "BAILIAN_IMAGE_REQUEST_REJECTED", "图片请求未被生成服务接受，请调整描述后重试。"
            )
        try:
            image_url = response.json()["data"][0]["url"]
        except (KeyError, IndexError, TypeError, ValueError):
            raise DigitalHumanImageProviderError(
                "BAILIAN_IMAGE_INVALID_RESPONSE", "图片生成服务返回了无法识别的结果。"
            ) from None
        if not isinstance(image_url, str) or not image_url:
            raise DigitalHumanImageProviderError(
                "BAILIAN_IMAGE_INVALID_RESPONSE", "图片生成服务返回了无法识别的结果。"
            )
        return image_url
