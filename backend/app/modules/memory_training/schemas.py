"""定义记忆训练 API DTO、Redis 会话 DTO 和模型出题结构。"""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from app.modules.memory_training.constants import (
    MAX_EXPLANATION_LENGTH,
    MAX_OPTION_TEXT_LENGTH,
    MAX_QUESTION_TEXT_LENGTH,
    OPTIONS_PER_QUESTION,
    QUESTION_COUNT,
)

SessionId = Annotated[str, StringConstraints(pattern=r"^[1-9][0-9]{0,18}$")]
OptionId = Literal["A", "B", "C", "D"]
TrainingState = Literal[
    "image_loading",
    "observing",
    "waiting_questions",
    "answering",
    "completed",
    "generation_failed",
]


class StrictSchema(BaseModel):
    """严格的 API 数据基类，拒绝未声明的客户端字段。"""

    model_config = ConfigDict(extra="forbid")


class TrainingQuestionOption(BaseModel):
    """已校验题目的选项及服务端生成的选项标识。"""

    model_config = ConfigDict(extra="forbid")

    id: OptionId = Field(description="服务端生成的选项标识")
    text: str = Field(min_length=1, max_length=MAX_OPTION_TEXT_LENGTH, description="选项文本")


class StoredTrainingQuestion(BaseModel):
    """Redis 内部题目，包含仅服务端可见的正确选项和解析。"""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="服务端生成的题目标识")
    prompt: str = Field(description="单选题题干")
    options: list[TrainingQuestionOption] = Field(description="四个单选选项")
    correct_option_id: OptionId = Field(description="服务端保存的唯一标准答案")
    explanation: str = Field(description="答案的图片事实依据")


class TrainingSessionState(BaseModel):
    """Redis 中保存的单次训练状态，不作为 API 响应直接返回。"""

    model_config = ConfigDict(extra="forbid")

    session_id: SessionId = Field(description="训练会话 ID")
    user_id: str = Field(description="会话所属用户 ID")
    image_url: str = Field(description="本次训练固定使用的图片公开链接")
    state: TrainingState = Field(description="服务端训练状态")
    observation_started_at: datetime | None = Field(default=None, description="观察开始时间")
    observation_deadline_at: datetime | None = Field(default=None, description="观察截止时间")
    questions: list[StoredTrainingQuestion] = Field(default_factory=list, description="内部题目")
    generation_error_code: str | None = Field(default=None, description="安全的出题失败代码")
    answers: dict[str, OptionId] | None = Field(default=None, description="用户最终答案")
    score: int | None = Field(default=None, ge=0, le=100, description="服务端计算的总分")
    correct_count: int | None = Field(default=None, ge=0, le=QUESTION_COUNT, description="答对题数")
    completed_at: datetime | None = Field(default=None, description="完成时间")


class GeneratedQuestion(BaseModel):
    """视觉模型的单题输出；服务端随后生成题目和选项 ID。"""

    model_config = ConfigDict(extra="forbid")

    prompt: str = Field(
        min_length=4, max_length=MAX_QUESTION_TEXT_LENGTH, description="图片细节题干"
    )
    options: list[str] = Field(
        min_length=OPTIONS_PER_QUESTION,
        max_length=OPTIONS_PER_QUESTION,
        description="按 A、B、C、D 顺序排列的选项文本",
    )
    correct_option_id: OptionId = Field(description="唯一正确选项，取值为 A、B、C 或 D")
    explanation: str = Field(
        min_length=4,
        max_length=MAX_EXPLANATION_LENGTH,
        description="指出图片直接可见依据的简短解析",
    )

    @field_validator("options")
    @classmethod
    def validate_distinct_options(cls, value: list[str]) -> list[str]:
        """拒绝空项及去除首尾空格后重复的选项。"""

        normalized = [option.strip().casefold() for option in value]
        if any(not option for option in normalized) or len(set(normalized)) != len(normalized):
            raise ValueError("每题必须包含四个非空且不同的选项。")
        return [option.strip() for option in value]


class GeneratedQuestionSet(BaseModel):
    """视觉模型必须一次返回完整的五道单选题。"""

    model_config = ConfigDict(extra="forbid")

    questions: list[GeneratedQuestion] = Field(
        min_length=QUESTION_COUNT,
        max_length=QUESTION_COUNT,
        description="恰好五道互不重复的视觉细节题",
    )

    @field_validator("questions")
    @classmethod
    def validate_distinct_questions(cls, value: list[GeneratedQuestion]) -> list[GeneratedQuestion]:
        """以规范化题干拒绝同一套题中的精确重复问题。"""

        normalized = [" ".join(question.prompt.split()).casefold() for question in value]
        if len(set(normalized)) != QUESTION_COUNT:
            raise ValueError("五道题目不能重复。")
        return value


class PreparationResponse(BaseModel):
    """训练准备页展示的固定规则，不包含图片信息。"""

    tool_name: str = Field(description="工具名称")
    description: str = Field(description="工具介绍")
    observation_seconds: int = Field(description="观察时长，秒")
    question_count: int = Field(description="单次题目数量")
    score_per_question: int = Field(description="答对单题得分")
    max_score: int = Field(description="单次最高分")


class SessionCreatedResponse(BaseModel):
    """创建会话后返回加载训练图片所需的最少信息。"""

    session_id: SessionId = Field(description="训练会话 ID")
    state: TrainingState = Field(description="初始训练状态")
    image_url: str = Field(description="本次训练图片公开访问链接")


class ObservationStartedResponse(BaseModel):
    """服务端确认观察开始后返回的权威时间信息。"""

    session_id: SessionId = Field(description="训练会话 ID")
    state: TrainingState = Field(description="当前训练状态")
    observation_started_at: datetime = Field(description="服务端记录的观察开始时刻")
    observation_deadline_at: datetime = Field(description="服务端记录的观察截止时刻")
    remaining_ms: int = Field(ge=0, description="服务端计算的剩余观察毫秒数")


class SessionStatusResponse(BaseModel):
    """用于轮询和刷新恢复的公开状态，不包含标准答案。"""

    session_id: SessionId = Field(description="训练会话 ID")
    state: TrainingState = Field(description="当前训练阶段")
    remaining_ms: int = Field(ge=0, description="观察剩余毫秒数，其他阶段为零")
    questions_ready: bool = Field(description="观察结束后是否可以获取题目")
    image_url: str | None = Field(default=None, description="仍可观察时返回的图片链接")
    error_code: str | None = Field(default=None, description="失败状态的安全业务代码")


class PublicQuestion(BaseModel):
    """答题阶段公开给浏览器的题目，不含答案或解析。"""

    id: str = Field(description="题目 ID")
    prompt: str = Field(description="题干")
    options: list[TrainingQuestionOption] = Field(description="四个选项")


class QuestionsResponse(BaseModel):
    """观察截止后可用的题目列表。"""

    questions: list[PublicQuestion] = Field(description="五道单选题")


class AnswerSubmissionRequest(StrictSchema):
    """最终答案请求，只接收题目 ID 到选项 ID 的映射。"""

    answers: dict[str, OptionId] = Field(
        min_length=QUESTION_COUNT,
        max_length=QUESTION_COUNT,
        description="恰好五道题的最终答案，不含用户或分数字段",
    )


class SubmissionSummaryResponse(BaseModel):
    """提交成功后的非答案成绩摘要。"""

    state: Literal["completed"] = Field(description="完成状态")
    score: int = Field(ge=0, le=100, description="总分")
    correct_count: int = Field(ge=0, le=QUESTION_COUNT, description="答对题数")
    question_count: int = Field(description="题目数量")


class QuestionReview(BaseModel):
    """结果页单题复盘，答案只在提交完成后返回。"""

    id: str = Field(description="题目 ID")
    prompt: str = Field(description="题干")
    user_option_id: OptionId = Field(description="用户选择的选项 ID")
    user_option_text: str = Field(description="用户选择的选项文本")
    correct_option_id: OptionId = Field(description="标准答案选项 ID")
    correct_option_text: str = Field(description="标准答案文本")
    is_correct: bool = Field(description="用户答案是否正确")
    score: Literal[0, 20] = Field(description="本题得分")
    explanation: str = Field(description="答案解析")


class TrainingResultResponse(BaseModel):
    """已完成训练的成绩、同一张原图链接和五题复盘。"""

    session_id: SessionId = Field(description="训练会话 ID")
    score: int = Field(ge=0, le=100, description="总分")
    correct_count: int = Field(ge=0, le=QUESTION_COUNT, description="答对题数")
    incorrect_count: int = Field(ge=0, le=QUESTION_COUNT, description="答错题数")
    correct_rate: float = Field(ge=0, le=1, description="正确率，范围 0 到 1")
    image_url: str = Field(description="本次观察图片的公开访问链接")
    questions: list[QuestionReview] = Field(description="五道题的作答及答案解析")
