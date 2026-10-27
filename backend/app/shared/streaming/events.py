"""与业务无关的公共 SSE 事件。"""

import json
from enum import StrEnum
from time import time_ns
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator


class EventType(StrEnum):
    """允许发送的四种协议事件。"""

    START = "start"
    MESSAGE = "message"
    HEARTBEAT = "heartbeat"
    END = "end"


class StreamEvent(BaseModel):
    """公共事件；仅含协议字段，消息种类由 data.type 表达。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: str = Field(
        default_factory=lambda: f"evt_{uuid4().hex}",
        pattern=r"^evt_[0-9a-f]{32}$",
        description="唯一事件标识",
    )
    event_type: EventType = Field(description="协议事件类型")
    timestamp: int = Field(
        default_factory=lambda: time_ns() // 1_000_000, ge=0, description="Unix 毫秒时间戳"
    )
    data: JsonValue = Field(default_factory=dict, description="JSON 兼容的事件内容")

    @model_validator(mode="after")
    def validate_message(self) -> "StreamEvent":
        """消息必须显式标明内容类型，其余事件保持数据结构自由。"""

        # JsonValue 限定结构，标准 JSON 检查额外排除 NaN 和无穷大。
        try:
            json.dumps(self.data, allow_nan=False)
        except ValueError as error:
            raise ValueError("event data must be JSON compatible") from error
        if self.event_type == EventType.MESSAGE and (
            not isinstance(self.data, dict)
            or not isinstance(self.data.get("type"), str)
            or not self.data["type"]
        ):
            raise ValueError("message data requires a non-empty type")
        return self
