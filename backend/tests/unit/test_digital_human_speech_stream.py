"""验证分段以及模拟 TTS 的并行和取消。"""

import asyncio

import pytest

from app.modules.digital_human.service.speech_stream import SpeechSegmenter, stream_speech
from app.shared.streaming import EventType, StreamEvent


def test_segments_and_flush():
    text = (
        "这是第一句完整的中文回答，接下来继续说明。第二句话包含数字 3.14 和 English words。最后一段"
    )
    segmenter = SpeechSegmenter()
    segments = []
    for char in text:
        segments.extend(segmenter.feed(char))
    segments.extend(segmenter.feed("", final=True))
    assert "".join(segments) == text
    assert len(segments) >= 2


def test_long_and_markdown():
    segments = SpeechSegmenter().feed("长" * 220, final=True)
    assert "".join(segments) == "长" * 220
    assert max(map(len, segments)) <= 100
    segments = SpeechSegmenter().feed(
        "这是一个 [链接](https://example.com/a.b)，欢迎访问。", final=True
    )
    assert "链接" in "".join(segments)
    assert "https://" not in "".join(segments)


@pytest.mark.anyio
async def test_audio_before_model_completion():
    release = asyncio.Event()

    async def source():
        yield StreamEvent(
            event_type=EventType.MESSAGE,
            data={"type": "text_delta", "content": "这是一段足够长的中文回复，"},
        )
        await release.wait()
        yield StreamEvent(
            event_type=EventType.MESSAGE, data={"type": "text_delta", "content": "后续回复结束。"}
        )

    class Speech:
        async def synthesize(self, text):
            return text.encode()

    stream = stream_speech(source(), Speech())
    assert (await anext(stream)).data["type"] == "text_delta"
    first = await asyncio.wait_for(anext(stream), 1)
    assert first.data["type"] == "audio_segment" and not release.is_set()
    release.set()
    remaining = [event async for event in stream]
    assert remaining[-1].data["type"] == "audio_done"
    assert [
        first.data["segment_id"],
        *[e.data["segment_id"] for e in remaining if e.data["type"] == "audio_segment"],
    ] == [1, 2]


@pytest.mark.anyio
async def test_tts_failure_keeps_text():
    async def source():
        for text in ["这是一段足够长的中文回复，", "接下来的文字仍然需要保存。"]:
            yield StreamEvent(
                event_type=EventType.MESSAGE, data={"type": "text_delta", "content": text}
            )

    class Speech:
        async def synthesize(self, text):
            raise RuntimeError("failed")

    events = [event async for event in stream_speech(source(), Speech())]
    assert sum(e.data["type"] == "text_delta" for e in events) == 2
    assert sum(e.data["type"] == "audio_error" for e in events) == 1
    assert events[-1].data["type"] == "audio_done"


@pytest.mark.anyio
async def test_close_cancels_tasks():
    started = asyncio.Event()
    closed = asyncio.Event()

    async def source():
        try:
            yield StreamEvent(
                event_type=EventType.MESSAGE,
                data={"type": "text_delta", "content": "这是一段足够长的中文回复，"},
            )
            await asyncio.Event().wait()
        finally:
            closed.set()

    class Speech:
        async def synthesize(self, text):
            started.set()
            await asyncio.Event().wait()

    stream = stream_speech(source(), Speech())
    await anext(stream)
    await asyncio.wait_for(started.wait(), 1)
    await asyncio.wait_for(stream.aclose(), 1)
    assert closed.is_set()


@pytest.mark.anyio
async def test_tts_timeout_keeps_text(monkeypatch):
    import app.modules.digital_human.service.speech_stream as speech_stream

    monkeypatch.setattr(speech_stream, "DIGITAL_HUMAN_TTS_REQUEST_TIMEOUT_SECONDS", 0.005)

    async def source():
        yield StreamEvent(
            event_type=EventType.MESSAGE,
            data={"type": "text_delta", "content": "这是一段足够长的中文回复，"},
        )

    class Speech:
        async def synthesize(self, text):
            await asyncio.Event().wait()

    events = [event async for event in stream_speech(source(), Speech())]
    assert [event.data["type"] for event in events] == ["text_delta", "audio_error", "audio_done"]


@pytest.mark.parametrize(
    "text",
    [
        "短文本",
        "这是混合 English 和中文的完整句子！！！后面还有内容。",
        "Visit https://example.com/path?a=3.14 and continue reading the page.",
        "这里有一段代码：\n```python\nprint('hello!')\n```\n接着继续说话。",
    ],
)
def test_streaming_text_boundaries(text):
    segmenter = SpeechSegmenter()
    segments = []
    for char in text:
        segments.extend(segmenter.feed(char))
    segments.extend(segmenter.feed("", final=True))
    assert all(segment for segment in segments)
    if "https://" in text:
        assert any("https://example.com/path?a=3.14" in segment for segment in segments)
    if "```" in text:
        assert "print" not in "".join(segments)


@pytest.mark.anyio
async def test_closed_conversation_stream_saves_partial_text(monkeypatch):
    from types import SimpleNamespace

    from app.agent.schemas import AgentTextDelta
    from app.modules.conversations.service.service import ConversationService

    class Agent:
        async def astream(self, *args, **kwargs):
            yield AgentTextDelta(content="已经生成的文字")
            await asyncio.Event().wait()

    saved = []
    service = ConversationService(
        session=None, agent=None, agent_registry={"digital_human": Agent()}
    )
    monkeypatch.setattr(
        service, "_save_partial_response", lambda prepared, text: saved.append(text)
    )
    monkeypatch.setattr(service, "_fail_idempotency_key", lambda prepared: None)

    async def finish_title(prepared, task):
        return None

    monkeypatch.setattr(service, "_finish_stream_title", finish_title)
    prepared = SimpleNamespace(
        cached_response_message=None,
        conversation=SimpleNamespace(id=2, skill_code="digital_human"),
        user_id=1,
        message_id=3,
        message_text="你好",
        should_generate_title=False,
        resume_answers=None,
    )
    stream = service.stream_turn(prepared, save_partial_on_cancel=True)
    assert (await anext(stream)).data["content"] == "已经生成的文字"
    await stream.aclose()
    assert saved == ["已经生成的文字"]
