import json

import httpx
import pytest

from app.core.config import Settings
from app.modules.digital_human.providers.errors import DigitalHumanProviderError
from app.modules.digital_human.providers.speech.asr import BailianAsrProvider
from app.modules.digital_human.providers.speech.tts import BailianTtsProvider


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "aliyun_bailian_api_key": "test-key",
        "aliyun_bailian_base_url": (
            "https://workspace.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
        ),
    }
    values.update(overrides)
    return Settings(**values)


@pytest.mark.anyio
async def test_asr_uses_workspace_endpoint_and_returns_text() -> None:
    requests: list[httpx.Request] = []

    async def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"output": {"text": "你好"}})

    provider = BailianAsrProvider(_settings(), transport=httpx.MockTransport(respond))

    text = await provider.transcribe(b"audio-bytes", content_type="audio/webm")

    assert text == "你好"
    assert str(requests[0].url) == (
        "https://workspace.cn-beijing.maas.aliyuncs.com/"
        "api/v1/services/aigc/multimodal-generation/generation"
    )
    assert requests[0].headers["authorization"] == "Bearer test-key"
    payload = json.loads(requests[0].content)
    assert payload["model"] == "qwen-audio-3.1-asr-flash"
    assert payload["input"]["messages"][0]["content"][0]["input_audio"]["data"].startswith(
        "data:audio/webm;base64,"
    )


@pytest.mark.anyio
async def test_tts_downloads_audio_from_trusted_bailian_result_host() -> None:
    requests: list[httpx.Request] = []

    async def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "POST":
            return httpx.Response(
                200,
                json={
                    "output": {
                        "audio": {
                            "url": "https://dashscope-result-bj.oss-cn-beijing.aliyuncs.com/audio.mp3"
                        }
                    }
                },
            )
        return httpx.Response(200, content=b"ID3-audio", headers={"Content-Type": "audio/mpeg"})

    provider = BailianTtsProvider(_settings(), transport=httpx.MockTransport(respond))

    audio = await provider.synthesize("你好")

    assert audio == b"ID3-audio"
    assert requests[0].headers["authorization"] == "Bearer test-key"
    payload = json.loads(requests[0].content)
    assert payload["model"] == "qwen-audio-3.1-tts-flash"
    assert payload["input"]["text"] == "你好"
    assert payload["input"]["voice"] == "xunanchuan_v3.1"
    assert requests[1].method == "GET"


@pytest.mark.anyio
async def test_tts_rejects_untrusted_download_url() -> None:
    async def respond(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"output": {"audio": {"url": "https://example.com/audio.mp3"}}},
        )

    provider = BailianTtsProvider(_settings(), transport=httpx.MockTransport(respond))

    with pytest.raises(DigitalHumanProviderError):
        await provider.synthesize("你好")


@pytest.mark.anyio
@pytest.mark.parametrize("malformed_payload", [[], {"output": []}, {"output": {"audio": []}}])
async def test_tts_rejects_malformed_response_payload(malformed_payload: object) -> None:
    async def respond(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=malformed_payload)

    provider = BailianTtsProvider(_settings(), transport=httpx.MockTransport(respond))

    with pytest.raises(DigitalHumanProviderError, match="没有返回有效音频"):
        await provider.synthesize("你好")


@pytest.mark.anyio
async def test_tts_rejects_audio_above_configured_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.modules.digital_human.providers.speech.tts.DIGITAL_HUMAN_MAX_TTS_AUDIO_BYTES",
        4,
    )

    async def respond(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(
                200,
                json={
                    "output": {
                        "audio": {
                            "url": "https://dashscope-result-bj.oss-cn-beijing.aliyuncs.com/audio.mp3"
                        }
                    }
                },
            )
        return httpx.Response(200, content=b"12345", headers={"Content-Type": "audio/mpeg"})

    provider = BailianTtsProvider(_settings(), transport=httpx.MockTransport(respond))

    with pytest.raises(DigitalHumanProviderError):
        await provider.synthesize("你好")
