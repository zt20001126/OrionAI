"""只从 TokenHub 指定腾讯云域名下载受限大小的图片结果。"""

from urllib.parse import urlparse

import httpx

from app.modules.agents.image_agent.providers.tokenhub_client import TokenHubImageError

_ALLOWED_DOMAIN_SUFFIX = ".myqcloud.com"
_DOWNLOAD_CHUNK_BYTES = 64 * 1024


class ImageResultDownloader:
    """限制下载域名、协议、重定向、MIME 类型和响应字节数。"""

    def __init__(
        self,
        *,
        timeout_seconds: float,
        max_bytes: int,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._timeout_seconds = timeout_seconds
        self._max_bytes = max_bytes
        self._transport = transport

    async def download(self, image_url: str) -> tuple[bytes, str]:
        _validate_image_url(image_url)
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(self._timeout_seconds),
                follow_redirects=False,
                transport=self._transport,
            ) as client:
                async with client.stream("GET", image_url) as response:
                    response.raise_for_status()
                    content_type = response.headers.get("content-type", "").split(";")[0].lower()
                    if content_type not in {"image/png", "image/jpeg"}:
                        raise TokenHubImageError(
                            "IMAGE_RESULT_INVALID_TYPE", "图片生成服务返回了不受支持的文件类型。"
                        )
                    content_length = response.headers.get("content-length")
                    if content_length is not None and int(content_length) > self._max_bytes:
                        raise TokenHubImageError(
                            "IMAGE_RESULT_TOO_LARGE", "生成图片超过系统允许的保存大小。"
                        )
                    chunks: list[bytes] = []
                    total = 0
                    async for chunk in response.aiter_bytes(_DOWNLOAD_CHUNK_BYTES):
                        total += len(chunk)
                        if total > self._max_bytes:
                            raise TokenHubImageError(
                                "IMAGE_RESULT_TOO_LARGE", "生成图片超过系统允许的保存大小。"
                            )
                        chunks.append(chunk)
        except TokenHubImageError:
            raise
        except (httpx.HTTPError, ValueError):
            raise TokenHubImageError(
                "IMAGE_RESULT_DOWNLOAD_FAILED", "图片已生成，但暂时无法保存结果，请稍后重试。"
            ) from None
        data = b"".join(chunks)
        if not data:
            raise TokenHubImageError("IMAGE_RESULT_EMPTY", "图片生成服务返回了空图片，请重试。")
        if (content_type == "image/png" and not data.startswith(b"\x89PNG\r\n\x1a\n")) or (
            content_type == "image/jpeg" and not data.startswith(b"\xff\xd8\xff")
        ):
            raise TokenHubImageError(
                "IMAGE_RESULT_INVALID_CONTENT", "图片生成服务返回的文件内容无效。"
            )
        return data, content_type


def _validate_image_url(image_url: str) -> None:
    try:
        parsed = urlparse(image_url)
        port = parsed.port
    except ValueError:
        raise TokenHubImageError(
            "IMAGE_RESULT_URL_REJECTED", "图片生成服务返回了无法安全读取的图片地址。"
        ) from None
    hostname = (parsed.hostname or "").lower()
    if (
        parsed.scheme != "https"
        or not hostname.endswith(_ALLOWED_DOMAIN_SUFFIX)
        or hostname == "myqcloud.com"
        or parsed.username is not None
        or parsed.password is not None
        or port not in (None, 443)
    ):
        raise TokenHubImageError(
            "IMAGE_RESULT_URL_REJECTED", "图片生成服务返回了无法安全读取的图片地址。"
        )
