from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.application import create_app
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.digital_human.dependencies.dependencies import get_digital_human_service
from app.modules.membership.dependencies import require_membership_access


class FakeDigitalHumanService:
    """记录语音 Router 转发的数据，不调用百炼。"""

    max_audio_bytes = 16

    def __init__(self) -> None:
        self.audio: bytes | None = None
        self.content_type: str | None = None
        self.synthesis_text: str | None = None

    async def transcribe(self, audio: bytes, *, content_type: str | None) -> str:
        self.audio = audio
        self.content_type = content_type
        return "识别结果"

    async def synthesize(self, text: str) -> bytes:
        self.synthesis_text = text
        return b"mp3-bytes"


@asynccontextmanager
async def _test_lifespan(_application: FastAPI) -> AsyncIterator[None]:
    yield


def test_speech_routes_reuse_auth_and_return_transient_audio() -> None:
    user = User(account="digital-human@example.com", password_hash="hash")
    service = FakeDigitalHumanService()
    application = create_app(lifespan=_test_lifespan)
    application.dependency_overrides[get_current_user] = lambda: user
    application.dependency_overrides[require_membership_access] = lambda: None
    application.dependency_overrides[get_digital_human_service] = lambda: service

    try:
        with TestClient(application) as client:
            recognition = client.post(
                "/api/digital-human/speech/recognitions",
                files={"file": ("recording.webm", b"webm-audio", "audio/webm")},
            )
            synthesis = client.post(
                "/api/digital-human/speech/syntheses",
                json={"text": "你好"},
            )

        assert recognition.status_code == 200
        assert recognition.json() == {"text": "识别结果"}
        assert service.audio == b"webm-audio"
        assert service.content_type == "audio/webm"
        assert synthesis.status_code == 200
        assert synthesis.content == b"mp3-bytes"
        assert synthesis.headers["content-type"] == "audio/mpeg"
        assert synthesis.headers["cache-control"] == "no-store"
        assert synthesis.headers["x-content-type-options"] == "nosniff"
        assert service.synthesis_text == "你好"
    finally:
        application.dependency_overrides.clear()
