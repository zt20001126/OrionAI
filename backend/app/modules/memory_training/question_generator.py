"""通过现有 OpenAI-compatible 模型 Provider 读取图片并生成严格结构化题目。"""

import json
import re

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
只输出一个 JSON 对象，且严格使用以下字段名称和结构：
{"questions":[{"prompt":"题干","options":["A选项","B选项","C选项","D选项"],"correct_option_id":"A","explanation":"图片证据"}]}
每道题都必须包含 prompt、options、correct_option_id、explanation 四个字段。
options 是按 A、B、C、D 顺序排列的四个纯文本选项；correct_option_id 只能是 A、B、C、D。
不要输出 id、question、answer 等其他字段，不要输出 Markdown、前言或 JSON 外的文字。
""".strip()

OPTION_IDS = ("A", "B", "C", "D")
_OPTION_ID_PATTERN = re.compile(
    r"^\s*(?:选项\s*)?([A-D])(?:\s*[.．、:：)）\-]\s*.*)?\s*$", re.IGNORECASE
)


class MemoryTrainingQuestionGenerator:
    """将图片 URL 送入项目当前配置模型，并转换为服务端私有题目 DTO。"""

    def __init__(self, model: BaseChatModel) -> None:
        self._model = model

    async def generate(self, image_url: str) -> list[StoredTrainingQuestion]:
        """生成、校验并分配服务端题目 ID。

        Step 1: 使用百炼兼容的 JSON Object 模式读取图片和生成题目。
        Step 2: 将模型字段归一化为服务端字段，再用 Pydantic 校验题量和选项。
        Step 3: 忽略模型生成的 ID，由服务端分配题目 ID 和选项 ID。
        """

        try:
            response = await self._model.bind(response_format={"type": "json_object"}).ainvoke(
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
        except Exception:
            raise MemoryTrainingUnavailableError(
                "视觉模型暂时无法生成题目。", code="MEMORY_TRAINING_MODEL_UNAVAILABLE"
            ) from None

        try:
            output_text = _extract_response_text(response.content)
            raw_output = json.loads(output_text)
            question_set = _parse_question_set(raw_output)
        except (ValidationError, TypeError, ValueError):
            raise MemoryTrainingUnavailableError(
                "模型返回的题目格式无效。", code="MEMORY_TRAINING_QUESTION_FORMAT_INVALID"
            ) from None

        return [
            StoredTrainingQuestion(
                id=f"q{question_index}",
                prompt=question.prompt.strip(),
                options=[
                    TrainingQuestionOption(id=OPTION_IDS[option_index], text=option_text)
                    for option_index, option_text in enumerate(question.options)
                ],
                correct_option_id=question.correct_option_id,
                explanation=question.explanation.strip(),
            )
            for question_index, question in enumerate(question_set.questions, start=1)
        ]


def _extract_response_text(content: object) -> str:
    """提取 OpenAI-compatible Chat Completions 返回的文本内容。"""

    if isinstance(content, str):
        return content
    if isinstance(content, list):
        text_blocks = [
            block["text"]
            for block in content
            if isinstance(block, dict)
            and block.get("type") == "text"
            and isinstance(block.get("text"), str)
        ]
        if text_blocks:
            return "\n".join(text_blocks)
    raise TypeError("模型响应不包含 JSON 文本。")


def _parse_question_set(output: object) -> GeneratedQuestionSet:
    """兼容百炼 JSON Object 输出别名，并统一校验为精简内部结构。"""

    if isinstance(output, list):
        raw_questions = output
    elif isinstance(output, dict):
        raw_questions = output.get("questions")
    else:
        raise TypeError("题目 JSON 根节点必须是对象或数组。")
    if not isinstance(raw_questions, list):
        raise TypeError("题目集合必须是数组。")

    normalized_questions = [_normalize_question(question) for question in raw_questions]
    return GeneratedQuestionSet.model_validate({"questions": normalized_questions})


def _normalize_question(question: object) -> dict[str, object]:
    """统一模型偶发使用的 question/answer 命名，不信任模型分配的 ID。"""

    if not isinstance(question, dict):
        raise TypeError("单题必须是对象。")
    prompt = question.get("prompt", question.get("question"))
    options = _normalize_options(question.get("options"))
    correct_option_id = _resolve_correct_option_id(question, options)
    return {
        "prompt": prompt,
        "options": options,
        "correct_option_id": correct_option_id,
        "explanation": question.get("explanation"),
    }


def _normalize_options(raw_options: object) -> list[str]:
    """将选项数组或 A-D 映射归一化为有序文本数组。"""

    if isinstance(raw_options, dict) and all(option_id in raw_options for option_id in OPTION_IDS):
        option_values = [raw_options[option_id] for option_id in OPTION_IDS]
    elif isinstance(raw_options, list):
        option_values = raw_options
    else:
        raise TypeError("选项必须是四项数组或 A-D 映射。")

    normalized: list[str] = []
    for option in option_values:
        if isinstance(option, str):
            normalized.append(option.strip())
            continue
        if isinstance(option, dict):
            text = option.get("text", option.get("value", option.get("option")))
            if isinstance(text, str):
                normalized.append(text.strip())
                continue
        raise TypeError("选项必须是文本。")
    return normalized


def _resolve_correct_option_id(question: dict[str, object], options: list[str]) -> str:
    """接受选项 ID、正确选项文本或明确的零基下标。"""

    if "correct_option_id" in question:
        answer = question["correct_option_id"]
    elif "correct_option_index" in question:
        index = question["correct_option_index"]
        if isinstance(index, int) and not isinstance(index, bool) and 0 <= index < len(OPTION_IDS):
            return OPTION_IDS[index]
        raise ValueError("正确选项下标无效。")
    else:
        answer = question.get("answer", question.get("correct_answer"))

    if isinstance(answer, dict):
        answer = answer.get("id", answer.get("option_id", answer.get("text")))
    if not isinstance(answer, str):
        raise TypeError("正确答案必须是选项 ID 或选项文本。")

    normalized_answer = " ".join(answer.split()).strip()
    for option_index, option_text in enumerate(options):
        if normalized_answer.casefold() == option_text.casefold():
            return OPTION_IDS[option_index]

    match = _OPTION_ID_PATTERN.fullmatch(normalized_answer)
    if match:
        return match.group(1).upper()
    raise ValueError("正确答案不能映射到 A-D 选项。")
