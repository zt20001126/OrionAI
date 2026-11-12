"""定义对话 HTTP 请求和响应 DTO，与 ORM 和 Agent 状态保持分离。"""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    FiniteFloat,
    StringConstraints,
    field_validator,
    model_validator,
)

from app.agent.schemas import KlineChartPayload, PlaceCardsPayload, QuestionPayload

NonEmptyText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20_000)
]


class ConversationCreateResponse(BaseModel):
    """新建会话后的公开字段。"""

    id: str = Field(description="Snowflake 会话 ID，以十进制字符串传输。")
    skill_code: str = Field(description="此会话绑定的技能代码。")
    title: str | None = Field(description="会话标题；新会话根据首条用户消息自动生成。")
    created_at: datetime = Field(description="创建时间。")
    updated_at: datetime = Field(description="最近更新时间。")


class ConversationListResponse(BaseModel):
    """分页会话列表。"""

    items: list[ConversationCreateResponse] = Field(description="按更新时间倒序排列的会话。")
    limit: int = Field(description="本页条数上限。")
    offset: int = Field(description="当前偏移量。")
    total_count: int = Field(description="当前用户的会话总数。")


class ConversationCreateRequest(BaseModel):
    """创建会话时可选指定已添加的技能。"""

    model_config = ConfigDict(extra="forbid")

    skill_code: str = Field(default="general_chat", min_length=1, max_length=100)


class MessageCreateRequest(BaseModel):
    """提交给 Agent 的纯文本消息。"""

    model_config = ConfigDict(extra="forbid")

    message: NonEmptyText = Field(description="用户消息文本。")


class UserLocationContext(BaseModel):
    """浏览器本轮定位上下文；由授权问答提交，不写入会话消息或用户资料。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["granted", "denied", "unavailable"] = Field(
        description="浏览器定位状态；granted 表示坐标由用户授权后获取。"
    )
    latitude: FiniteFloat | None = Field(
        default=None, ge=-90, le=90, description="浏览器返回的纬度，仅 granted 时提供。"
    )
    longitude: FiniteFloat | None = Field(
        default=None, ge=-180, le=180, description="浏览器返回的经度，仅 granted 时提供。"
    )
    accuracy_meters: FiniteFloat | None = Field(
        default=None, ge=0, description="浏览器报告的水平精度（米），仅 granted 时提供。"
    )

    @model_validator(mode="after")
    def validate_coordinates(self) -> "UserLocationContext":
        """确保授权状态与坐标字段成组出现，供对话 API 边界校验。"""
        coordinates = (self.latitude, self.longitude, self.accuracy_meters)
        if self.status == "granted" and any(value is None for value in coordinates):
            raise ValueError("定位成功时必须提供经纬度和精度。")
        if self.status != "granted" and any(value is not None for value in coordinates):
            raise ValueError("定位未成功时不能携带坐标。")
        return self


class QuestionAnswersRequest(BaseModel):
    """题卡答案及可选的数字人浏览器定位结果。"""

    model_config = ConfigDict(extra="forbid")

    answers: dict[str, str] = Field(min_length=1, description="题目 ID 到选项标签的映射。")
    location: UserLocationContext | None = Field(
        default=None, description="数字人授权题卡提交的浏览器定位结果，仅用于本轮。"
    )

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


class SubmittedQuestionAnswer(BaseModel):
    """用户提交的单道题答案，用于稳定恢复会话中的答题展示。"""

    model_config = ConfigDict(extra="forbid")

    question_id: str = Field(min_length=1, description="原题目 ID。")
    question: str = Field(min_length=1, description="原题目文本。")
    answer: str = Field(min_length=1, description="用户实际选择的选项。")


class QuestionAnswersContentPart(BaseModel):
    """用户提交答案时随文本消息保存的结构化展示数据。"""

    model_config = ConfigDict(extra="forbid")

    type: Literal["question_answers"] = Field(description="结构化答题结果类型。")
    items: list[SubmittedQuestionAnswer] = Field(min_length=1, description="题目和用户答案。")


class ImageResultContentPart(BaseModel):
    """消息中指向当前用户私有图片结果接口的稳定引用。"""

    model_config = ConfigDict(extra="forbid")

    type: Literal["image_result"] = Field(description="生图结果内容类型。")
    task_result_id: str = Field(pattern=r"^[0-9]{1,20}$", description="图片任务结果 ID。")
    generation_status: Literal["succeeded"] = Field(description="图片生成状态。")
    image_url: str = Field(description="需要登录后访问的图片接口相对路径。")


class VideoResultContentPart(BaseModel):
    """消息中指向当前用户私有视频结果的稳定引用。"""

    model_config = ConfigDict(extra="forbid")

    type: Literal["video_result"]
    task_result_id: str = Field(pattern=r"^[0-9]{1,20}$")
    generation_status: Literal["succeeded"]
    video_url: str


class KlineChartContentPart(BaseModel):
    """持久化K线图数据，历史消息与流式事件共用同一 payload。"""

    model_config = ConfigDict(extra="forbid")

    type: Literal["kline_chart"]
    content: KlineChartPayload


class PlaceCardsContentPart(BaseModel):
    """持久化附近商家卡片数据，供实时及历史消息使用。"""

    model_config = ConfigDict(extra="forbid")

    type: Literal["place_cards"]
    data: PlaceCardsPayload


class RoutePoint(BaseModel):
    """路线端点名称和高德 GCJ-02 坐标。"""

    name: str = Field(min_length=1, max_length=200)
    location: str = Field(min_length=3, max_length=64)


class RouteStep(BaseModel):
    """高德返回的分段导航指示和距离。"""

    instruction: str
    distance_m: int = Field(ge=0)
    polyline: str | None = None


class RouteResult(BaseModel):
    """路线卡片和会话历史共用的数据结构。"""

    mode: Literal["walking", "cycling", "driving"]
    origin: RoutePoint
    destination: RoutePoint
    distance_m: int = Field(ge=0)
    duration_s: int = Field(ge=0)
    steps: list[RouteStep]


class PlaceRouteRequest(BaseModel):
    """用户授权的浏览器位置、路线方式与选定商家的高德坐标。"""

    model_config = ConfigDict(extra="forbid")
    latitude: FiniteFloat = Field(ge=-90, le=90)
    longitude: FiniteFloat = Field(ge=-180, le=180)
    mode: Literal["walking", "cycling", "driving"] = Field(
        default="walking", description="路线方式；旧请求省略时继续按步行规划。"
    )
    destination: str = Field(min_length=3, max_length=64)
    destination_name: str = Field(min_length=1, max_length=200)
    destination_id: str | None = Field(default=None, max_length=100)
    request_id: str = Field(pattern=r"^[0-9a-fA-F-]{36}$", description="路线请求的重试标识。")


class RouteResultContentPart(BaseModel):
    """保存路线结果以支持历史消息恢复。"""

    type: Literal["route_result"]
    data: RouteResult
    request_id: str | None = Field(default=None, description="按钮请求标识，用于重试去重。")


MessageContentPart = Annotated[
    TextContentPart
    | QuestionContentPart
    | QuestionAnswersContentPart
    | ImageResultContentPart
    | VideoResultContentPart
    | KlineChartContentPart
    | PlaceCardsContentPart
    | RouteResultContentPart,
    Field(discriminator="type"),
]


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
    skill_code: str = Field(description="该会话绑定的技能代码。")
    limit: int = Field(description="本页条数上限。")
    offset: int = Field(description="当前偏移量。")


class AgentTurnResponse(BaseModel):
    """一次聊天执行的状态及新生成的助手消息。"""

    status: Literal["completed", "waiting"] = Field(description="回答完成或等待用户选择。")
    message: MessageResponse = Field(description="本轮新生成的助手消息。")


class ConversationRunResponse(BaseModel):
    """异步对话任务创建响应，返回可供监听与中断使用的标识。"""

    run_id: str = Field(description="本轮生成任务的唯一标识，状态保存在 Redis。")


class ConversationTextDeltaEvent(BaseModel):
    """流式回答中的一个文本增量。"""

    type: Literal["text_delta"] = Field(description="文本增量事件。")
    content: str = Field(min_length=1, description="本次新增的助手文本。")


class ConversationQuestionEvent(BaseModel):
    """Agent 需要用户选择时发送的完整题卡消息。"""

    type: Literal["question"] = Field(description="题卡事件。")
    message: MessageResponse = Field(description="已持久化的题卡助手消息。")


class ConversationKlineChartEvent(BaseModel):
    """SSE 中完整传输一份K线图数据；调用方：会话流服务。"""

    model_config = ConfigDict(extra="forbid")

    type: Literal["kline_chart"]
    content: KlineChartPayload


class ConversationPlaceCardsEvent(BaseModel):
    """SSE 中完整传输一组附近商家卡片；调用方：会话流服务。"""

    model_config = ConfigDict(extra="forbid")

    type: Literal["place_cards"]
    data: PlaceCardsPayload
