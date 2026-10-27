"""定义 Agent 内部调用和结构化题卡协议，不复用 HTTP 或 ORM 模型。"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.agent.config import DEFAULT_MAX_INPUT_CHARS, MAX_QUESTIONS_PER_BATCH, QUESTION_OPTION_COUNT


class AgentRequest(BaseModel):
    """单轮 Agent 调用输入；对话历史由 LangGraph Checkpointer 管理。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    message: str = Field(
        min_length=1,
        max_length=DEFAULT_MAX_INPUT_CHARS,
        description="本轮用户文本，不能为空且不能超过输入长度上限。",
    )


class QuestionOption(BaseModel):
    """题卡中的一个单选项，包含用户可选标签及解释。"""

    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1, max_length=100, description="用户提交的选项标签。")
    description: str = Field(min_length=1, max_length=240, description="选项含义的简短说明。")

    @field_validator("label", "description")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        """去除两端空白并拒绝空值或多行选项文本。"""

        normalized = value.strip()
        if not normalized or "\n" in normalized or "\r" in normalized:
            raise ValueError("题卡选项必须是非空单行文本。")
        return normalized


class Question(BaseModel):
    """基础对话 Agent 使用的单选题及其固定选项。"""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[a-z][a-z0-9_]{0,63}$",
        description="批次内唯一的 snake_case 题目标识。",
    )
    title: str = Field(min_length=1, max_length=100, description="题目完整标题。")
    type: Literal["SingleChoice"] = Field(description="基础对话题卡仅支持单选。")
    options: list[QuestionOption] = Field(
        min_length=QUESTION_OPTION_COUNT,
        max_length=QUESTION_OPTION_COUNT,
        description=f"必须提供 {QUESTION_OPTION_COUNT} 个不同选项。",
    )
    allow_custom_input: Literal[False] = Field(description="固定为 false，不接收自定义输入。")

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        """去除题目首尾空格，拒绝空标题及多行标题。"""

        normalized = value.strip()
        if not normalized or "\n" in normalized or "\r" in normalized:
            raise ValueError("题目标题必须是非空单行文本。")
        return normalized

    @model_validator(mode="after")
    def validate_unique_labels(self) -> "Question":
        """确保四个选项标签不重复。"""

        labels = [option.label.casefold() for option in self.options]
        if len(set(labels)) != len(labels):
            raise ValueError("题卡选项标签不能重复。")
        return self


class QuestionPayload(BaseModel):
    """一次等待交互中的 1–3 道题卡，并提供严格答案校验。"""

    model_config = ConfigDict(extra="forbid")

    questions: list[Question] = Field(
        min_length=1,
        max_length=MAX_QUESTIONS_PER_BATCH,
        description=f"当前题卡批次，数量为 1–{MAX_QUESTIONS_PER_BATCH} 道。",
    )

    @model_validator(mode="after")
    def validate_unique_question_ids(self) -> "QuestionPayload":
        """拒绝同一批题卡中重复的 question ID。"""

        question_ids = [question.id for question in self.questions]
        if len(set(question_ids)) != len(question_ids):
            raise ValueError("题卡 question ID 不能重复。")
        return self

    def validate_answers(self, answers: dict[str, Any]) -> None:
        """校验答案题目集合和选项标签与当前题卡完全匹配。"""

        expected_ids = {question.id for question in self.questions}
        if set(answers) != expected_ids:
            raise ValueError("答案必须与当前题卡的问题 ID 完全匹配。")

        for question in self.questions:
            answer = answers[question.id]
            option_labels = {option.label for option in question.options}
            if not isinstance(answer, str) or answer not in option_labels:
                raise ValueError("单选题答案必须是该题的一个有效选项标签。")


class AgentResponse(BaseModel):
    """Agent 稳定结果；completed 携带回答，waiting 携带待展示题卡。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    agent: str = Field(description="生成此结果的 Agent 标识。")
    status: Literal["completed", "waiting"] = Field(
        description="completed 表示回答完成；waiting 表示需要用户选择题卡。"
    )
    answer: str | None = Field(default=None, description="完成状态下的助手文本回答。")
    questions: QuestionPayload | None = Field(default=None, description="等待状态下的单选题卡。")
    image_result_id: str | None = Field(
        default=None,
        pattern=r"^[0-9]{1,20}$",
        description="可选的私有图片任务结果 ID。",
    )

    @model_validator(mode="after")
    def validate_result_state(self) -> "AgentResponse":
        """确保回答文本与待答题卡仅出现在相应状态中。"""

        if self.status == "completed":
            if self.answer is None or not self.answer.strip() or self.questions is not None:
                raise ValueError("completed 结果必须只包含非空 answer。")
        elif self.answer is not None or self.questions is None or self.image_result_id is not None:
            raise ValueError("waiting 结果必须只包含 questions。")
        return self


class AgentTextDelta(BaseModel):
    """Agent 流中的一段用户可见文本。"""

    type: Literal["text_delta"] = "text_delta"
    content: str = Field(min_length=1, description="本次新增的助手文本。")


class AgentStreamResult(BaseModel):
    """Agent 流完成后得到的正式结果。"""

    type: Literal["result"] = "result"
    response: AgentResponse = Field(description="本轮完整回答或待答题卡。")


AgentStreamEvent = AgentTextDelta | AgentStreamResult
