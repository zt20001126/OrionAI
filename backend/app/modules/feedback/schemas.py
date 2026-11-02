"""定义问题反馈 API 的输入与统一消息响应结构。"""

from pydantic import BaseModel, ConfigDict, Field, field_validator


class FeedbackRequest(BaseModel):
    """接收用户提交的问题反馈内容，不接受用户提供的身份字段。"""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(
        min_length=1,
        max_length=100,
        description="反馈标题，去除首尾空白后为 1 至 100 个字符",
    )
    content: str = Field(
        min_length=1,
        max_length=2000,
        description="反馈详情，去除首尾空白后为 1 至 2000 个字符",
    )

    @field_validator("title", mode="before")
    @classmethod
    def trim_and_check_title(cls, value: object) -> object:
        """去除首尾空白，并拒绝可能影响邮件头的标题控制字符。"""

        if not isinstance(value, str):
            return value
        normalized = value.strip()
        if any(ord(character) < 32 or ord(character) == 127 for character in normalized):
            raise ValueError("标题不能包含控制字符。")
        return normalized

    @field_validator("content", mode="before")
    @classmethod
    def trim_content(cls, value: object) -> object:
        """去除反馈内容首尾空白，保留中间换行以支持复现步骤。"""

        if not isinstance(value, str):
            return value
        normalized = value.strip()
        return normalized


class FeedbackResponse(BaseModel):
    """反馈邮件发送成功后的简短 API 响应。"""

    message: str = Field(description="操作结果说明")
