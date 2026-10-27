"""流式响应、空闲心跳及事件生命周期。"""

import asyncio
import logging
import math
from collections.abc import AsyncIterator
from contextlib import suppress

from starlette.responses import StreamingResponse

from app.shared.streaming.encoder import encode_event
from app.shared.streaming.events import EventType, StreamEvent

logger = logging.getLogger(__name__)
DEFAULT_HEARTBEAT_SECONDS = 15.0


async def stream_events(
    messages: AsyncIterator[StreamEvent],
    *,
    heartbeat_seconds: float = DEFAULT_HEARTBEAT_SECONDS,
) -> AsyncIterator[bytes]:
    """为消息流补齐开始、结束与空闲心跳，并关闭上游生成器。"""

    if not math.isfinite(heartbeat_seconds) or heartbeat_seconds <= 0:
        raise ValueError("heartbeat_seconds must be a finite positive number")

    iterator = messages.__aiter__()
    pending: asyncio.Task[StreamEvent] | None = None
    try:
        yield encode_event(StreamEvent(event_type=EventType.START))
        while True:
            pending = asyncio.create_task(anext(iterator))
            while True:
                done, _ = await asyncio.wait({pending}, timeout=heartbeat_seconds)
                if done:
                    break
                # 等待期间只发送心跳；业务事件一到即优先发送业务事件。
                if pending.done():
                    break
                yield encode_event(StreamEvent(event_type=EventType.HEARTBEAT))
            try:
                event = pending.result()
            except StopAsyncIteration:
                break
            if event.event_type != EventType.MESSAGE:
                raise ValueError("message source may only yield message events")
            yield encode_event(event)
        yield encode_event(StreamEvent(event_type=EventType.END, data={"status": "completed"}))
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("sse_stream_failed")
        # 错误详情只留在服务端日志中，避免泄露上游异常或堆栈。
        yield encode_event(StreamEvent(event_type=EventType.END, data={"status": "failed"}))
    finally:
        if pending is not None and not pending.done():
            pending.cancel()
            with suppress(asyncio.CancelledError):
                await pending
        close = getattr(iterator, "aclose", None)
        if close is not None:
            try:
                await close()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("sse_source_close_failed")


def create_sse_response(
    messages: AsyncIterator[StreamEvent],
    *,
    heartbeat_seconds: float = DEFAULT_HEARTBEAT_SECONDS,
) -> StreamingResponse:
    """创建无需业务依赖的 Starlette SSE 响应。"""

    if not math.isfinite(heartbeat_seconds) or heartbeat_seconds <= 0:
        raise ValueError("heartbeat_seconds must be a finite positive number")
    return StreamingResponse(
        stream_events(messages, heartbeat_seconds=heartbeat_seconds),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )
