"""通用 SSE 组件的协议与资源清理测试。"""

import asyncio
import json
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.shared.streaming import (
    EventType,
    StreamEvent,
    create_sse_response,
    encode_event,
    stream_events,
)


def _decode(frame: bytes) -> dict[str, object]:
    lines = frame.decode("utf-8").splitlines()
    assert lines[:3][0].startswith("id: ")
    assert lines[:3][1].startswith("event: ")
    assert lines[:3][2].startswith("data: ")
    return json.loads(lines[2][6:])


def test_event_types_and_validation() -> None:
    for event_type in EventType:
        data = {"type": "text"} if event_type == EventType.MESSAGE else {}
        assert StreamEvent(event_type=event_type, data=data).event_type == event_type
    with pytest.raises(ValidationError):
        StreamEvent(event_type="status")
    with pytest.raises(ValidationError):
        StreamEvent(event_type=EventType.MESSAGE, data={})
    with pytest.raises(ValidationError):
        StreamEvent(event_type=EventType.START, data={"invalid": object()})
    with pytest.raises(ValidationError):
        StreamEvent(event_type=EventType.START, run_id="business")
    with pytest.raises(ValidationError):
        StreamEvent(event_id="evt_invalid\ndata: injected", event_type=EventType.START)
    with pytest.raises(ValidationError):
        StreamEvent(event_type=EventType.MESSAGE, data={"type": "text", "value": float("nan")})


def test_event_ids_timestamps_and_utf8_encoding() -> None:
    first = StreamEvent(
        event_type=EventType.MESSAGE, data={"type": "text", "content": "你好\n世界"}
    )
    second = StreamEvent(event_type=EventType.MESSAGE, data={"type": "image", "url": "/x"})
    assert first.event_id.startswith("evt_") and first.event_id != second.event_id
    assert first.timestamp > 1_000_000_000_000
    assert set(first.model_dump()) == {"event_id", "event_type", "timestamp", "data"}
    frame = encode_event(first)
    assert frame.startswith(f"id: {first.event_id}\nevent: message\ndata: ".encode())
    assert frame.endswith(b"\n\n")
    assert b"\xe4\xbd\xa0\xe5\xa5\xbd" in frame
    assert _decode(frame) == first.model_dump(mode="json")
    assert frame.count(b"\ndata: ") == 1


@pytest.mark.anyio
async def test_order_lifecycle_and_response_headers() -> None:
    async def messages() -> AsyncIterator[StreamEvent]:
        yield StreamEvent(event_type=EventType.MESSAGE, data={"type": "text", "content": "一"})
        yield StreamEvent(event_type=EventType.MESSAGE, data={"type": "text", "content": "二"})

    response = create_sse_response(messages())
    assert response.media_type == "text/event-stream"
    assert response.headers["cache-control"] == "no-cache, no-transform"
    assert response.headers["x-accel-buffering"] == "no"
    events = [_decode(frame) async for frame in response.body_iterator]
    assert [event["event_type"] for event in events] == ["start", "message", "message", "end"]
    assert events[-1]["data"] == {"status": "completed"}


@pytest.mark.anyio
async def test_idle_heartbeat_stops_after_source_ends() -> None:
    release = asyncio.Event()
    closed = asyncio.Event()

    async def messages() -> AsyncIterator[StreamEvent]:
        try:
            await release.wait()
            yield StreamEvent(event_type=EventType.MESSAGE, data={"type": "text", "content": "ok"})
        finally:
            closed.set()

    stream = stream_events(messages(), heartbeat_seconds=0.001)
    assert _decode(await anext(stream))["event_type"] == "start"
    assert _decode(await asyncio.wait_for(anext(stream), 1))["event_type"] == "heartbeat"
    release.set()
    remaining = [_decode(frame) async for frame in stream]
    assert [event["event_type"] for event in remaining] == ["message", "end"]
    assert closed.is_set()


@pytest.mark.anyio
async def test_failure_sends_one_sanitized_end_and_closes_source() -> None:
    closed = asyncio.Event()

    async def messages() -> AsyncIterator[StreamEvent]:
        try:
            yield StreamEvent(event_type=EventType.MESSAGE, data={"type": "text", "content": "ok"})
            raise RuntimeError("private stack detail")
        finally:
            closed.set()

    frames = [frame async for frame in stream_events(messages())]
    events = [_decode(frame) for frame in frames]
    assert [event["event_type"] for event in events] == ["start", "message", "end"]
    assert events[-1]["data"] == {"status": "failed"}
    assert b"private stack detail" not in b"".join(frames)
    assert closed.is_set()


@pytest.mark.anyio
async def test_source_cannot_duplicate_terminal_event() -> None:
    async def messages() -> AsyncIterator[StreamEvent]:
        yield StreamEvent(event_type=EventType.END, data={"status": "completed"})

    events = [_decode(frame) async for frame in stream_events(messages())]
    assert [event["event_type"] for event in events] == ["start", "end"]
    assert events[-1]["data"] == {"status": "failed"}


@pytest.mark.anyio
async def test_cancellation_closes_pending_source_without_end() -> None:
    waiting = asyncio.Event()
    closed = asyncio.Event()

    async def messages() -> AsyncIterator[StreamEvent]:
        try:
            waiting.set()
            await asyncio.Event().wait()
            yield StreamEvent(event_type=EventType.MESSAGE, data={"type": "text"})
        finally:
            closed.set()

    stream = stream_events(messages())
    assert _decode(await anext(stream))["event_type"] == "start"
    delivery = asyncio.create_task(anext(stream))
    await asyncio.wait_for(waiting.wait(), 1)
    delivery.cancel()
    with pytest.raises(asyncio.CancelledError):
        await delivery
    await asyncio.wait_for(closed.wait(), 1)
    await stream.aclose()


@pytest.mark.anyio
async def test_asgi_client_disconnect_closes_source() -> None:
    started = asyncio.Event()
    disconnected = asyncio.Event()
    closed = asyncio.Event()
    sent: list[dict[str, object]] = []

    async def messages() -> AsyncIterator[StreamEvent]:
        try:
            started.set()
            await asyncio.Event().wait()
            yield StreamEvent(event_type=EventType.MESSAGE, data={"type": "text"})
        finally:
            closed.set()

    async def receive() -> dict[str, str]:
        await disconnected.wait()
        return {"type": "http.disconnect"}

    async def send(message: dict[str, object]) -> None:
        sent.append(message)

    response = create_sse_response(messages())
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
    }
    delivery = asyncio.create_task(response(scope, receive, send))
    await asyncio.wait_for(started.wait(), 1)
    disconnected.set()
    await asyncio.wait_for(delivery, 1)
    assert closed.is_set()
    frames = [item["body"] for item in sent if item["type"] == "http.response.body"]
    assert [event["event_type"] for event in map(_decode, frames)] == ["start"]


def test_streaming_package_has_no_agent_dependency() -> None:
    source_dir = Path(__file__).resolve().parents[2] / "app" / "shared" / "streaming"
    assert all(
        "app.agent" not in path.read_text(encoding="utf-8") for path in source_dir.glob("*.py")
    )
