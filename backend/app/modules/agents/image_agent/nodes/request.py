"""判断用户需求并生成图片助手本轮的回复或工具调用。"""

import logging
import uuid
from typing import Any, Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.config import get_stream_writer

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
_GENERATION_REPLY_FALLBACK = "我正在根据你的描述生成图片，请稍候。"
_STREAM_REPLY_PROMPT = (
    "你是 OrionAI 图片助手。请用简体中文向用户作简短、自然的回复。"
    "如果用户要求生成图片，说明你将按其描述开始生成，不要声称图片已经生成。"
    "如果用户提出其他请求，只说明图片助手能做什么，并引导用户描述商品和画面效果。"
    "不要编造商品信息，不要使用 Markdown。"
)
logger = logging.getLogger(__name__)
_SIZE_QUESTION = Question(
    id="image_size",
    title="请选择本次生成图片的画幅比例。",
    type="SingleChoice",
    options=[QuestionOption(**option) for option in SIZE_QUESTION_OPTIONS],
    allow_custom_input=False,
)


def create_request_node(chat_model: Any, system_prompt: str | None = None):
    """创建需求节点，分类并直接组织非生图回复或图片工具调用。"""
    structured_model = chat_model.with_structured_output(
        ImageRequestAnalysis,
        method="json_mode",
    )
    prompt = system_prompt or load_image_agent_prompt()

    async def request(
        state: ImageAgentState,
        config: RunnableConfig | None = None,
    ) -> dict[str, object]:
        configurable = dict((config or {}).get("configurable") or {})
        resume_answers = configurable.get("resume_answers", {})

        # 题卡恢复时沿用已保存的提示词和参数，避免把画幅答案重新识别成新需求。
        if state.get("awaiting_image_size") and isinstance(resume_answers, dict) and resume_answers:
            tool_call = _create_image_tool_call(
                state,
                configurable=configurable,
                resume_answers=resume_answers,
            )
            if configurable.get("stream_response") is True and _has_image_tool_call(tool_call):
                reply = await _stream_reply(
                    chat_model,
                    state.get("original_request", ""),
                    fallback=_GENERATION_REPLY_FALLBACK,
                    config=config,
                )
                return {**tool_call, "answer": reply}
            return tool_call

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
            if configurable.get("stream_response") is True:
                reply = await _stream_reply(
                    chat_model,
                    request_text,
                    fallback=reply,
                    config=config,
                )
            return {
                "messages": [AIMessage(content=reply)],
                "original_request": request_text,
                "is_image_generation": False,
                "awaiting_image_size": False,
                "task_result_id": None,
                "image_result_id": None,
                "answer": reply,
            }

        image_prompt = (result.image_prompt.strip() or request_text)[:IMAGE_PROMPT_MAX_LENGTH]
        tool_call = _create_image_tool_call(
            state,
            configurable=configurable,
            original_request=request_text,
            image_prompt=image_prompt,
        )
        if configurable.get("stream_response") is True and _has_image_tool_call(tool_call):
            reply = await _stream_reply(
                chat_model,
                request_text,
                fallback=_GENERATION_REPLY_FALLBACK,
                config=config,
            )
            return {**tool_call, "answer": reply}
        return tool_call

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

    # 新一轮请求使用本轮输入；仅题卡恢复时沿用已保存参数。
    if resume_answers is not None:
        options = state.get("generation_options") or extract_image_options(resolved_request)
        options = apply_size_answer(options, resume_answers)
        task_result_id = state.get("task_result_id") or str(generate_snowflake_id())
    else:
        options = extract_image_options(resolved_request)
        options = (
            ImageGenerationOptions(**options).validate_exclusivity().model_dump(exclude_none=True)
        )
        task_result_id = str(generate_snowflake_id())

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
            "image_result_id": None,
            "is_image_generation": True,
            "awaiting_image_size": True,
            "answer": "",
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
        "image_result_id": None,
        "is_image_generation": True,
        "awaiting_image_size": False,
        "answer": "",
    }


def _has_image_tool_call(result: dict[str, object]) -> bool:
    """确认当前节点已准备调用生图工具，而不是等待用户选择画幅。"""

    messages = result.get("messages")
    if not isinstance(messages, list) or not messages:
        return False
    tool_calls = getattr(messages[-1], "tool_calls", [])
    return any(call.get("name") == "generate_image" for call in tool_calls)


async def _stream_reply(
    chat_model: Any,
    request_text: str,
    *,
    fallback: str,
    config: RunnableConfig | None,
) -> str:
    """流式生成面向用户的回复，并把每段文字写入 LangGraph 自定义流。"""

    writer = get_stream_writer()
    answer = ""
    messages = [
        SystemMessage(content=_STREAM_REPLY_PROMPT),
        HumanMessage(content=request_text),
    ]
    try:
        async for chunk in chat_model.astream(messages, config=config):
            content = getattr(chunk, "content", "")
            if isinstance(content, str):
                delta = content
            elif isinstance(content, list):
                delta = "".join(
                    block["text"]
                    for block in content
                    if isinstance(block, dict) and isinstance(block.get("text"), str)
                )
            else:
                delta = ""
            delta = delta[: max(0, IMAGE_RESPONSE_MAX_LENGTH - len(answer))]
            if delta:
                answer += delta
                writer({"type": "text_delta", "content": delta})
            if len(answer) >= IMAGE_RESPONSE_MAX_LENGTH:
                break
    except Exception as error:
        logger.warning("image_agent_reply_stream_failed error_type=%s", type(error).__name__)
        if not answer:
            answer = fallback[:IMAGE_RESPONSE_MAX_LENGTH]
            writer({"type": "text_delta", "content": answer})

    return answer.strip() or fallback[:IMAGE_RESPONSE_MAX_LENGTH]


RequestRoute = Literal["tool_node", "output_node"]


def route_after_request(state: ImageAgentState) -> RequestRoute:
    """按需求节点产出的意图选择生图工具路径或直接回复路径。"""
    return "tool_node" if state.get("is_image_generation") else "output_node"
