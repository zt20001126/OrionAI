"""调用 TokenHub Hy-Image API 并将上游异常映射为安全错误。"""

import logging
from collections.abc import Mapping
from typing import Any

import httpx

from app.core.config import Settings
from app.modules.image_generation.schemas import ImageGenerationOptions, TokenHubImageResult

logger = logging.getLogger(__name__)


class TokenHubImageError(Exception):
    """只携带稳定错误码和可展示提示，不保存上游响应正文。"""

    def __init__(self, code: str, public_message: str, request_id: str | None = None) -> None:
        super().__init__(public_message)
        self.code = code
        self.public_message = public_message
        self.request_id = request_id


class TokenHubImageClient:
    """使用注入设置发起图片生成请求，可注入 HTTP transport 测试。"""

    def __init__(
        self,
        settings: Settings,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._settings = settings
        self._transport = transport

    async def generate(
        self,
        *,
        prompt: str,
        options: ImageGenerationOptions,
        session_id: str,
    ) -> TokenHubImageResult:
        api_key = self._settings.tokenhub_api_key.get_secret_value().strip()
        if not api_key:
            raise TokenHubImageError(
                "TOKENHUB_NOT_CONFIGURED", "图片生成服务尚未完成配置，请联系管理员。"
            )

        request_body: dict[str, Any] = {
            "model": self._settings.tencent_hy_image_model,
            "messages": [{"role": "user", "content": [{"type": "text", "text": prompt}]}],
            "session": session_id,
        }
        if options.size is not None:
            request_body["size"] = options.size
        if options.generate_max_pixels is not None:
            request_body["generate_max_pixels"] = options.generate_max_pixels
        if options.seed is not None:
            request_body["seed"] = options.seed
        if options.footnote is not None:
            request_body["footnote"] = options.footnote
        if options.use_search_tool:
            request_body["use_search_tool"] = {"value": True}

        endpoint = (
            self._settings.tokenhub_base_url.rstrip("/")
            + "/"
            + self._settings.tencent_hy_image_endpoint.lstrip("/")
        )
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(self._settings.tokenhub_timeout_seconds),
                transport=self._transport,
            ) as client:
                response = await client.post(
                    endpoint,
                    headers={"Authorization": f"Bearer {api_key}"},
                    json=request_body,
                )
        except httpx.TimeoutException:
            raise TokenHubImageError(
                "TOKENHUB_TIMEOUT", "图片生成服务响应超时，请稍后重试。"
            ) from None
        except httpx.HTTPError:
            raise TokenHubImageError(
                "TOKENHUB_CONNECTION_FAILED", "暂时无法连接图片生成服务，请稍后重试。"
            ) from None

        request_id = _request_id(response)
        status_messages = {
            401: ("TOKENHUB_AUTH_FAILED", "图片生成服务鉴权失败，请联系管理员。"),
            422: ("TOKENHUB_CONTENT_REJECTED", "图片请求未通过内容安全检查，请调整描述后重试。"),
            429: ("TOKENHUB_RATE_LIMITED", "图片生成请求较多，请稍后重试。"),
        }
        if response.status_code in status_messages:
            code, message = status_messages[response.status_code]
            raise TokenHubImageError(code, message, request_id)
        if response.status_code >= 500:
            raise TokenHubImageError(
                "TOKENHUB_UNAVAILABLE", "图片生成服务暂时不可用，请稍后重试。", request_id
            )
        if response.is_error:
            raise TokenHubImageError(
                "TOKENHUB_REQUEST_REJECTED", "图片请求参数未被图片生成服务接受。", request_id
            )

        try:
            body = response.json()
            image = body["choices"][0]["delta"]["image"]
            result = TokenHubImageResult(
                image_url=image["url"],
                width=image.get("width"),
                height=image.get("height"),
                request_id=body.get("request_id") or request_id,
                provider_model=body.get("model"),
                metadata={
                    "usage_total_tokens": _usage_tokens(body),
                },
            )
        except (KeyError, IndexError, TypeError, ValueError):
            raise TokenHubImageError(
                "TOKENHUB_INVALID_RESPONSE", "图片生成服务返回了无法识别的结果。", request_id
            ) from None
        return result


def _request_id(response: httpx.Response) -> str | None:
    header_id = response.headers.get("x-request-id")
    if header_id:
        return header_id[:256]
    try:
        body = response.json()
    except ValueError:
        return None
    value = body.get("request_id") if isinstance(body, Mapping) else None
    return value[:256] if isinstance(value, str) else None


def _usage_tokens(body: Mapping[str, Any]) -> int | None:
    usage = body.get("tokenhub_usage")
    tokens = usage.get("total_tokens") if isinstance(usage, Mapping) else None
    return tokens if isinstance(tokens, int) and tokens >= 0 else None
