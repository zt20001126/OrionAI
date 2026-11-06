"""安全下载百炼生成的短期图片地址。"""

import httpx

from app.modules.digital_human.providers.image_generation import DigitalHumanImageProviderError

_CHUNK_BYTES = 64 * 1024


class BailianImageResultDownloader:
    """限制百炼图片结果的格式、响应大小和重定向。"""

    def __init__(
        self,
        *,
        timeout_seconds: float,
        max_bytes: int,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """设置图片下载超时、最大字节数及可选 HTTP transport。"""
        self._timeout_seconds = timeout_seconds
        self._max_bytes = max_bytes
        self._transport = transport

    async def download(self, image_url: str) -> tuple[bytes, str]:
        """下载并校验 PNG/JPEG；输入百炼临时地址，输出字节与 MIME 类型。"""
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
                        raise DigitalHumanImageProviderError(
                            "BAILIAN_IMAGE_INVALID_TYPE", "生成服务返回了不受支持的图片格式。"
                        )
                    content_length = response.headers.get("content-length")
                    if content_length is not None and int(content_length) > self._max_bytes:
                        raise DigitalHumanImageProviderError(
                            "BAILIAN_IMAGE_TOO_LARGE", "生成图片超过系统允许的保存大小。"
                        )
                    chunks: list[bytes] = []
                    total_bytes = 0
                    async for chunk in response.aiter_bytes(_CHUNK_BYTES):
                        total_bytes += len(chunk)
                        if total_bytes > self._max_bytes:
                            raise DigitalHumanImageProviderError(
                                "BAILIAN_IMAGE_TOO_LARGE", "生成图片超过系统允许的保存大小。"
                            )
                        chunks.append(chunk)
        except DigitalHumanImageProviderError:
            raise
        except (httpx.HTTPError, ValueError):
            raise DigitalHumanImageProviderError(
                "BAILIAN_IMAGE_DOWNLOAD_FAILED", "图片已生成，但暂时无法保存结果，请稍后重试。"
            ) from None

        image_data = b"".join(chunks)
        if not image_data:
            raise DigitalHumanImageProviderError(
                "BAILIAN_IMAGE_EMPTY", "图片生成服务返回了空图片，请重试。"
            )
        valid_signature = (
            image_data.startswith(b"\x89PNG\r\n\x1a\n")
            if content_type == "image/png"
            else image_data.startswith(b"\xff\xd8\xff")
        )
        if not valid_signature:
            raise DigitalHumanImageProviderError(
                "BAILIAN_IMAGE_INVALID_CONTENT", "图片生成服务返回的文件内容无效。"
            )
        return image_data, content_type
