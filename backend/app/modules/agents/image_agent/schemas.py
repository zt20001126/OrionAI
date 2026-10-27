"""图片助手模型输出、TokenHub 参数和结果协议。"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.agents.image_agent.constants import (
    IMAGE_PROMPT_MAX_LENGTH,
    IMAGE_RESPONSE_MAX_LENGTH,
)


class ImageRequestAnalysis(BaseModel):
    """图片助手需求判断结果，包含意图、图片提示词和非生图回复。"""

    model_config = ConfigDict(extra="forbid")

    intent: Literal["generate_image", "other"] = Field(description="用户本轮需求类别")
    image_prompt: str = Field(
        default="",
        max_length=IMAGE_PROMPT_MAX_LENGTH,
        description="生图请求对应的商品图片画面提示词；其他请求留空",
    )
    reply: str = Field(
        default="",
        max_length=IMAGE_RESPONSE_MAX_LENGTH,
        description="非生图请求的简短中文回复；生图请求留空",
    )
