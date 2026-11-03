import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.infrastructure.database.base import Base
from app.modules.digital_human.service.errors import (
    DigitalHumanPayloadTooLargeError,
    DigitalHumanValidationError,
)
from app.modules.digital_human.service.service import DigitalHumanService


class FakeAsrProvider:
    def __init__(self, text: str) -> None:
        self.text = text
        self.calls: list[tuple[bytes, str]] = []

    async def transcribe(self, audio: bytes, *, content_type: str) -> str:
        self.calls.append((audio, content_type))
        return self.text


class FakeTtsProvider:
    def __init__(self, audio: bytes = b"audio") -> None:
        self.audio = audio
        self.calls: list[str] = []

    async def synthesize(self, text: str) -> bytes:
        self.calls.append(text)
        return self.audio


@pytest.mark.anyio
async def test_transcription_validates_audio_and_returns_provider_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.modules.digital_human.service.service.DIGITAL_HUMAN_MAX_AUDIO_BYTES",
        16,
    )
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    provider = FakeAsrProvider("  明天上午开会。  ")
    service = DigitalHumanService(
        session=Session(engine),
        settings=Settings(),
        asr_provider=provider,
        tts_provider=FakeTtsProvider(),
    )
    try:
        assert await service.transcribe(b"webm-bytes", content_type="audio/webm;codecs=opus") == (
            "明天上午开会。"
        )
        assert provider.calls == [(b"webm-bytes", "audio/webm")]
        with pytest.raises(DigitalHumanPayloadTooLargeError):
            await service.transcribe(b"x" * 17, content_type="audio/webm")
        with pytest.raises(DigitalHumanValidationError):
            await service.transcribe(b"data", content_type="application/octet-stream")
        assert len(provider.calls) == 1
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.mark.anyio
async def test_synthesis_rejects_empty_or_overlong_text_before_provider_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.modules.digital_human.service.service.DIGITAL_HUMAN_MAX_TTS_TEXT_CHARS",
        3,
    )
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    provider = FakeTtsProvider()
    session = Session(engine)
    service = DigitalHumanService(
        session=session,
        settings=Settings(),
        asr_provider=FakeAsrProvider("recognized"),
        tts_provider=provider,
    )
    try:
        assert await service.synthesize("  你好  ") == b"audio"
        assert provider.calls == ["你好"]
        with pytest.raises(DigitalHumanValidationError):
            await service.synthesize("   ")
        with pytest.raises(DigitalHumanValidationError):
            await service.synthesize("太长了一点")
        assert provider.calls == ["你好"]
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()
