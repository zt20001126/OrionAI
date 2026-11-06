"""阿里云百炼非实时 TTS Provider。"""

import logging
import re
from typing import Protocol
from urllib.parse import urlsplit, urlunsplit

import httpx

from app.core.config import Settings
from app.modules.digital_human.constants import (
    DIGITAL_HUMAN_MAX_TTS_AUDIO_BYTES,
    DIGITAL_HUMAN_TTS_DOWNLOAD_TIMEOUT_SECONDS,
    DIGITAL_HUMAN_TTS_MODEL,
    DIGITAL_HUMAN_TTS_REQUEST_TIMEOUT_SECONDS,
    DIGITAL_HUMAN_TTS_VOICE,
)
from app.modules.digital_human.providers.base import (
    get_bailian_request_context,
    raise_provider_error,
)
from app.modules.digital_human.providers.errors import DigitalHumanProviderError

logger = logging.getLogger(__name__)
TTS_PATH = "/api/v1/services/audio/tts/SpeechSynthesizer"
TRUSTED_AUDIO_HOST = re.compile(r"^dashscope-result-[a-z0-9-]+\.oss-[a-z0-9-]+\.aliyuncs\.com$")


class TtsProvider(Protocol):
    """输入一段文本并返回非持久化音频字节。"""

    async def synthesize(self, text: str) -> bytes: ...


class BailianTtsProvider:
    """调用 Qwen-Audio-TTS 并将有时效的生成音频下载后交给 Service。"""

    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._settings = settings
        self._transport = transport

    async def synthesize(self, text: str) -> bytes:
        origin, api_key = get_bailian_request_context(self._settings)
        request_timeout = DIGITAL_HUMAN_TTS_REQUEST_TIMEOUT_SECONDS
        download_timeout = DIGITAL_HUMAN_TTS_DOWNLOAD_TIMEOUT_SECONDS
        payload = {
            "model": DIGITAL_HUMAN_TTS_MODEL,
            "input": {
                "text": text,
                "voice": DIGITAL_HUMAN_TTS_VOICE,
                "format": "mp3",
                "sample_rate": 24000,
            },
        }
        try:
            async with httpx.AsyncClient(
                timeout=max(request_timeout, download_timeout), transport=self._transport
            ) as client:
                response = await client.post(
                    f"{origin}{TTS_PATH}",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                    timeout=request_timeout,
                )
                response.raise_for_status()
                result = response.json()
                output = result.get("output") if isinstance(result, dict) else None
                audio_result = output.get("audio") if isinstance(output, dict) else None
                audio_url = audio_result.get("url") if isinstance(audio_result, dict) else None
                if not isinstance(audio_url, str):
                    raise DigitalHumanProviderError("语音合成没有返回有效音频。")
                download_url = _trusted_download_url(audio_url)
                async with client.stream(
                    "GET", download_url, timeout=download_timeout
                ) as audio_response:
                    audio_response.raise_for_status()
                    content_type = audio_response.headers.get("content-type", "").split(";")[0]
                    if content_type and not content_type.startswith("audio/"):
                        raise DigitalHumanProviderError("语音合成返回了无效的音频格式。")
                    content_length = audio_response.headers.get("content-length")
                    if content_length and int(content_length) > DIGITAL_HUMAN_MAX_TTS_AUDIO_BYTES:
                        raise DigitalHumanProviderError("生成的语音文件超过大小限制。")
                    audio = bytearray()
                    async for chunk in audio_response.aiter_bytes():
                        audio.extend(chunk)
                        if len(audio) > DIGITAL_HUMAN_MAX_TTS_AUDIO_BYTES:
                            raise DigitalHumanProviderError("生成的语音文件超过大小限制。")
        except DigitalHumanProviderError:
            raise
        except (httpx.HTTPError, ValueError, TypeError) as error:
            logger.warning("digital_human_tts_provider_failed error_type=%s", type(error).__name__)
            raise raise_provider_error(error) from None
        if not audio:
            raise DigitalHumanProviderError("语音合成返回了空音频。")
        return bytes(audio)


def _trusted_download_url(value: str) -> str:
    parsed_url = urlsplit(value)
    hostname = (parsed_url.hostname or "").lower()
    try:
        port = parsed_url.port
    except ValueError:
        raise DigitalHumanProviderError("语音服务返回的音频地址无效。") from None
    if (
        parsed_url.scheme not in {"http", "https"}
        or parsed_url.username is not None
        or parsed_url.password is not None
        or port not in {None, 80, 443}
        or not TRUSTED_AUDIO_HOST.fullmatch(hostname)
    ):
        raise DigitalHumanProviderError("语音服务返回的音频地址无效。")
    # 百炼示例可能返回 HTTP URL；同一受信任对象域名统一升级为 HTTPS。
    return urlunsplit(("https", hostname, parsed_url.path, parsed_url.query, ""))
