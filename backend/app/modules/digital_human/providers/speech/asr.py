"""阿里云百炼非实时 ASR Provider。"""

import base64
import logging
from typing import Protocol

import httpx

from app.core.config import Settings
from app.modules.digital_human.constants import (
    DIGITAL_HUMAN_ASR_MODEL,
    DIGITAL_HUMAN_ASR_TIMEOUT_SECONDS,
)
from app.modules.digital_human.providers.base import (
    get_bailian_request_context,
    raise_provider_error,
)
from app.modules.digital_human.providers.errors import DigitalHumanProviderError

logger = logging.getLogger(__name__)
ASR_PATH = "/api/v1/services/aigc/multimodal-generation/generation"


class AsrProvider(Protocol):
    """接收短音频字节并返回识别文本。"""

    async def transcribe(self, audio: bytes, *, content_type: str) -> str: ...


class BailianAsrProvider:
    """将短音频编码为 Data URI 并调用百炼 Qwen-Audio-ASR。"""

    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._settings = settings
        self._transport = transport

    async def transcribe(self, audio: bytes, *, content_type: str) -> str:
        origin, api_key = get_bailian_request_context(self._settings)
        encoded_audio = base64.b64encode(audio).decode("ascii")
        data_uri = f"data:{content_type};base64,{encoded_audio}"
        payload = {
            "model": DIGITAL_HUMAN_ASR_MODEL,
            "input": {
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "input_audio",
                                "input_audio": {"data": data_uri},
                            }
                        ],
                    }
                ]
            },
            "parameters": {"format": _audio_format(content_type)},
        }
        try:
            async with httpx.AsyncClient(
                timeout=DIGITAL_HUMAN_ASR_TIMEOUT_SECONDS,
                transport=self._transport,
            ) as client:
                response = await client.post(
                    f"{origin}{ASR_PATH}",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                        "X-DashScope-SSE": "disable",
                    },
                    json=payload,
                )
            response.raise_for_status()
            result = response.json()
        except (httpx.HTTPError, ValueError) as error:
            status_code = (
                error.response.status_code if isinstance(error, httpx.HTTPStatusError) else None
            )
            logger.warning(
                "digital_human_asr_provider_failed error_type=%s status_code=%s",
                type(error).__name__,
                status_code,
            )
            raise raise_provider_error(error) from None

        output = result.get("output") if isinstance(result, dict) else None
        text = output.get("text") if isinstance(output, dict) else None
        if not isinstance(text, str):
            sentence = output.get("sentence") if isinstance(output, dict) else None
            text = sentence.get("text") if isinstance(sentence, dict) else None
        if not isinstance(text, str):
            raise DigitalHumanProviderError("语音识别没有返回有效文本，请重试。")
        return text.strip()


def _audio_format(content_type: str) -> str:
    subtype = content_type.split(";", maxsplit=1)[0].removeprefix("audio/").lower()
    return {"mpeg": "mp3", "x-wav": "wav", "ogg": "opus"}.get(subtype, subtype)
