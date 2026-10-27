"""定义对话 HTTP 请求和响应 DTO，与 ORM 和 Agent 状态保持分离。"""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from app.agent.schemas import QuestionPayload

NonEmptyText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20_000)
]


class ConversationCreateResponse(BaseModel):
    """新建会话后的公开字段。"""

    id: str = Field(description="Snowflake 会话 ID，以十进制字符串传输。")
    title: str | None = Field(description="会话标题；新会话根据首条用户消息自动生成。")
    created_at: datetime = Field(description="创建时间。")
    updated_at: datetime = Field(description="最近更新时间。")


class ConversationListResponse(BaseModel):
    """分页会话列表。"""

    items: list[ConversationCreateResponse] = Field(description="按更新时间倒序排列的会话。")
    limit: int = Field(description="本页条数上限。")
    offset: int = Field(description="当前偏移量。")


class MessageCreateRequest(BaseModel):
    """提交给 Agent 的纯文本消息。"""

    model_config = ConfigDict(extra="forbid")

    message: NonEmptyText = Field(description="用户消息文本。")


class QuestionAnswersRequest(BaseModel):
    """题卡答案，键为 question ID，值为对应选项标签。"""

    model_config = ConfigDict(extra="forbid")

    answers: dict[str, str] = Field(min_length=1, description="题目 ID 到选项标签的映射。")

    @field_validator("answers")
    @classmethod
    def validate_answer_text(cls, answers: dict[str, str]) -> dict[str, str]:
        """拒绝空白题目 ID 或答案。"""

        if any(
            not question_id.strip() or not answer.strip() for question_id, answer in answers.items()
        ):
            raise ValueError("答案 ID 和选项标签不能为空。")
        return answers


class TextContentPart(BaseModel):
    """消息中的文本内容部分。"""

    model_config = ConfigDict(extra="forbid")

    type: Literal["text"] = Field(description="文本内容类型。")
    text: str = Field(description="消息文本。")


class QuestionContentPart(BaseModel):
    """等待用户选择时保存的结构化题卡部分。"""

    model_config = ConfigDict(extra="forbid")

    type: Literal["question"] = Field(description="题卡内容类型。")
    questions: list[dict[str, object]] = Field(description="题卡问题及选项。")

    @classmethod
    def from_payload(cls, payload: QuestionPayload) -> "QuestionContentPart":
        """将 Agent 题卡转换为可写入 JSONB 的 API 内容部分。"""

        return cls(type="question", questions=payload.model_dump(mode="json")["questions"])


MessageContentPart = Annotated[TextContentPart | QuestionContentPart, Field(discriminator="type")]


class MessageContent(BaseModel):
    """采用 parts 数组保存一条消息的多种内容部分。"""

    model_config = ConfigDict(extra="forbid")

    parts: list[MessageContentPart] = Field(min_length=1, description="消息内容部分。")


class MessageResponse(BaseModel):
    """用户可见消息记录。"""

    id: str = Field(description="Snowflake 消息 ID，以十进制字符串传输。")
    conversation_id: str = Field(description="所属会话 Snowflake ID，以十进制字符串传输。")
    role: Literal["user", "assistant"] = Field(description="消息角色。")
    content: MessageContent = Field(description="符合 parts 结构的 JSON 消息内容。")
    created_at: datetime = Field(description="创建时间。")


class MessageListResponse(BaseModel):
    """按消息 ID 升序返回的分页消息。"""

    items: list[MessageResponse] = Field(description="消息列表。")
    limit: int = Field(description="本页条数上限。")
    offset: int = Field(description="当前偏移量。")


class AgentTurnResponse(BaseModel):
    """一次聊天执行的状态及新生成的助手消息。"""

    status: Literal["completed", "waiting"] = Field(description="回答完成或等待用户选择。")
    message: MessageResponse = Field(description="本轮新生成的助手消息。")
