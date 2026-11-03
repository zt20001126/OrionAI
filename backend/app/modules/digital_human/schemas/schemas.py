"""定义数字人历史和语音请求/响应 DTO。"""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

TtsText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class DigitalHumanConversationSummary(BaseModel):
    """数字人历史列表中的会话摘要。"""

    id: str
    skill_code: str
    title: str | None
    created_at: datetime
    updated_at: datetime


class DigitalHumanConversationListResponse(BaseModel):
    """当前用户的数字人会话分页。"""

    items: list[DigitalHumanConversationSummary]
    limit: int
    offset: int
    total_count: int


class TranscriptionResponse(BaseModel):
    """ASR 返回的可编辑转写文本。"""

    text: str


class SynthesisRequest(BaseModel):
    """TTS 输入文本。"""

    text: TtsText = Field(description="需要合成的助手文本。")
