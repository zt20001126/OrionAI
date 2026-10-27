"""判断用户需求并生成图片助手本轮的回复或工具调用。"""

import uuid
from typing import Any, Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from app.agent.errors import AgentConfigurationError, AgentExecutionError
from app.agent.schemas import Question, QuestionOption
from app.infrastructure.database.snowflake import generate_snowflake_id
from app.modules.agents.image_agent.constants import (
    IMAGE_PROMPT_MAX_LENGTH,
    IMAGE_REQUEST_MAX_LENGTH,
    IMAGE_RESPONSE_MAX_LENGTH,
)
from app.modules.agents.image_agent.parameter_policy import (
    SIZE_QUESTION_OPTIONS,
    apply_size_answer,
    extract_image_options,
)
from app.modules.agents.image_agent.prompts.loader import load_image_agent_prompt
from app.modules.agents.image_agent.schemas import ImageRequestAnalysis
from app.modules.agents.image_agent.state import ImageAgentState
from app.modules.image_generation.schemas import ImageGenerationOptions

_OTHER_REQUEST_FALLBACK = (
    "我是图片助手，可以根据文字帮你生成商品主图或详情页图片。请告诉我商品信息和希望的画面效果。"
)
_SIZE_QUESTION = Question(
    id="image_size",
    title="请选择本次生成图片的画幅比例。",
    type="SingleChoice",
    options=[QuestionOption(**option) for option in SIZE_QUESTION_OPTIONS],
    allow_custom_input=False,
)


def create_request_node(chat_model: Any, system_prompt: str | None = None):
    """创建需求节点，分类并直接组织非生图回复或图片工具调用。"""
    structured_model = chat_model.with_structured_output(ImageRequestAnalysis)
    prompt = system_prompt or load_image_agent_prompt()

    async def request(
        state: ImageAgentState,
        config: RunnableConfig | None = None,
    ) -> dict[str, object]:
        configurable = dict((config or {}).get("configurable") or {})
        resume_answers = configurable.get("resume_answers", {})

        # 题卡恢复时沿用已保存的提示词和参数，避免把画幅答案重新识别成新需求。
        if state.get("awaiting_image_size") and isinstance(resume_answers, dict) and resume_answers:
            return _create_image_tool_call(
                state,
                configurable=configurable,
                resume_answers=resume_answers,
            )

        message = next(
            (
                item
                for item in reversed(state.get("messages", []))
                if isinstance(item, HumanMessage)
            ),
            None,
        )
        if message is None or not isinstance(message.content, str):
            raise AgentExecutionError("图片助手未收到有效文本。", code="invalid_image_request")

        request_text = message.content.strip()
        if not request_text or len(request_text) > IMAGE_REQUEST_MAX_LENGTH:
            raise AgentExecutionError("图片助手输入文本无效。", code="invalid_image_request")

        try:
            analysis = await structured_model.ainvoke(
                [SystemMessage(content=prompt), HumanMessage(content=request_text)]
            )
            result = ImageRequestAnalysis.model_validate(analysis)
        except Exception:
            raise AgentExecutionError(
                "图片助手暂时无法理解本次请求。", code="image_request_analysis_failed"
            ) from None

        if result.intent == "other":
            reply = result.reply.strip()[:IMAGE_RESPONSE_MAX_LENGTH] or _OTHER_REQUEST_FALLBACK
            return {
                "messages": [AIMessage(content=reply)],
                "original_request": request_text,
                "is_image_generation": False,
                "awaiting_image_size": False,
            }

        image_prompt = (result.image_prompt.strip() or request_text)[:IMAGE_PROMPT_MAX_LENGTH]
        return _create_image_tool_call(
            state,
            configurable=configurable,
            original_request=request_text,
            image_prompt=image_prompt,
        )

    return request


def _create_image_tool_call(
    state: ImageAgentState,
    *,
    configurable: dict[str, Any],
    original_request: str | None = None,
    image_prompt: str | None = None,
    resume_answers: dict[str, Any] | None = None,
) -> dict[str, object]:
    """校验图片任务参数，并构造题卡或生图工具调用。"""
    user_id = configurable.get("user_id")
    conversation_id = configurable.get("conversation_id")
    run_id = configurable.get("run_id")
    if not all(isinstance(value, int) and value > 0 for value in (user_id, conversation_id)):
        raise AgentConfigurationError(
            "图片助手缺少可信用户或会话标识。", code="missing_image_run_identity"
        )
    if not isinstance(run_id, str) or not run_id:
        raise AgentConfigurationError("图片助手缺少运行标识。", code="missing_image_run_id")

    resolved_request = original_request or state.get("original_request", "")
    resolved_prompt = (image_prompt or state.get("image_prompt", "") or resolved_request)[
        :IMAGE_PROMPT_MAX_LENGTH
    ]
    if not resolved_prompt:
        raise AgentExecutionError("没有可用于生成图片的商品描述。", code="empty_image_prompt")

    options = state.get("generation_options") or extract_image_options(resolved_request)
    if resume_answers is not None:
        options = apply_size_answer(options, resume_answers)
    else:
        options = (
            ImageGenerationOptions(**options).validate_exclusivity().model_dump(exclude_none=True)
        )

    task_result_id = state.get("task_result_id") or str(generate_snowflake_id())
    if "size" not in options and "generate_max_pixels" not in options:
        tool_call = {
            "name": "ask_user_questions",
            "args": {"questions": [_SIZE_QUESTION.model_dump(mode="json")]},
            "id": uuid.uuid4().hex,
            "type": "tool_call",
        }
        return {
            "messages": [AIMessage(content="", tool_calls=[tool_call])],
            "original_request": resolved_request,
            "image_prompt": resolved_prompt,
            "generation_options": options,
            "task_result_id": task_result_id,
            "is_image_generation": True,
            "awaiting_image_size": True,
        }

    tool_call = {
        "name": "generate_image",
        "args": {
            "task_result_id": task_result_id,
            "user_id": user_id,
            "conversation_id": conversation_id,
            "prompt": resolved_prompt,
            **options,
        },
        "id": uuid.uuid4().hex,
        "type": "tool_call",
    }
    return {
        "messages": [AIMessage(content="", tool_calls=[tool_call])],
        "original_request": resolved_request,
        "image_prompt": resolved_prompt,
        "generation_options": options,
        "task_result_id": task_result_id,
        "is_image_generation": True,
        "awaiting_image_size": False,
    }


RequestRoute = Literal["tool_node", "output_node"]


def route_after_request(state: ImageAgentState) -> RequestRoute:
    """按需求节点产出的意图选择生图工具路径或直接回复路径。"""
    return "tool_node" if state.get("is_image_generation") else "output_node"
