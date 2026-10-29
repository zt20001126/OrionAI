"""通过现有 OpenAI-compatible 模型 Provider 读取图片并生成严格结构化题目。"""

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import ValidationError

from app.modules.memory_training.errors import MemoryTrainingUnavailableError
from app.modules.memory_training.schemas import (
    GeneratedQuestionSet,
    StoredTrainingQuestion,
    TrainingQuestionOption,
)

QUESTION_SYSTEM_PROMPT = """
你是视觉记忆训练的出题器。只根据用户消息附带的这张图片出题。
生成恰好 5 道简体中文单选题，每题恰好 4 个不同选项，并且只有一个正确选项。
问题只询问图片直接可观察的信息，例如颜色、数量、动作、位置、空间关系或明显细节。
不得使用图片之外的知识，不得猜测模糊或看不清的内容。
五道题应考查不同的可见细节。每题解析用一句话指出图片中支持答案的直接证据。
严格返回指定 JSON 结构，不输出 Markdown 或其他文字。
""".strip()

OPTION_IDS = ("A", "B", "C", "D")


class MemoryTrainingQuestionGenerator:
    """将图片 URL 送入项目当前配置模型，并转换为服务端私有题目 DTO。"""

    def __init__(self, model: BaseChatModel) -> None:
        self._model = model

    async def generate(self, image_url: str) -> list[StoredTrainingQuestion]:
        """生成、校验并分配服务端题目 ID。

        Step 1: 使用当前模型 Provider 的 JSON mode 按 Pydantic Schema 生成五道题。
        Step 2: 再次校验结构、题量和选项，避免 Provider 返回未校验对象。
        Step 3: 由服务端分配固定题目 ID 和选项 ID，返回内部含答案的 DTO。
        """

        structured_model = self._model.with_structured_output(
            GeneratedQuestionSet,
            method="json_mode",
        )
        try:
            output = await structured_model.ainvoke(
                [
                    SystemMessage(content=QUESTION_SYSTEM_PROMPT),
                    HumanMessage(
                        content=[
                            {"type": "text", "text": "请观察图片并按要求生成训练问题。"},
                            {"type": "image_url", "image_url": {"url": image_url}},
                        ]
                    ),
                ]
            )
            question_set = GeneratedQuestionSet.model_validate(output)
        except (ValidationError, TypeError, ValueError):
            raise MemoryTrainingUnavailableError(
                "模型返回的题目格式无效。", code="MEMORY_TRAINING_QUESTION_FORMAT_INVALID"
            ) from None
        except Exception:
            raise MemoryTrainingUnavailableError(
                "视觉模型暂时无法生成题目。", code="MEMORY_TRAINING_MODEL_UNAVAILABLE"
            ) from None

        return [
            StoredTrainingQuestion(
                id=f"q{question_index}",
                prompt=question.prompt.strip(),
                options=[
                    TrainingQuestionOption(id=OPTION_IDS[option_index], text=option_text)
                    for option_index, option_text in enumerate(question.options)
                ],
                correct_option_id=OPTION_IDS[question.correct_option_index],
                explanation=question.explanation.strip(),
            )
            for question_index, question in enumerate(question_set.questions, start=1)
        ]
