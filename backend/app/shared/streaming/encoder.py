"""SSE 协议编码边界。"""

import json

from app.shared.streaming.events import StreamEvent


def encode_event(event: StreamEvent) -> bytes:
    """将单个事件编码为 UTF-8 SSE 帧。"""

    payload = json.dumps(event.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":"))
    # JSON 将内容中的换行转义，因而 data 始终是一条合法的 SSE 字段行。
    return f"id: {event.event_id}\nevent: {event.event_type.value}\ndata: {payload}\n\n".encode()
