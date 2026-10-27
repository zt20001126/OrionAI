"""抽取画幅参数；需要补充画幅时复用共享题卡工具。"""

import uuid

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig

from app.agent.errors import AgentConfigurationError, AgentExecutionError
from app.agent.schemas import Question, QuestionOption
from app.infrastructure.database.snowflake import generate_snowflake_id
from app.modules.agents.image_agent.parameter_policy import (
    SIZE_QUESTION_OPTIONS,
    apply_size_answer,
    extract_image_options,
)
from app.modules.agents.image_agent.schemas import ImageGenerationOptions
from app.modules.agents.image_agent.state import ImageAgentState

SIZE_QUESTION = Question(
    id="image_size",
    title="请选择本次生成图片的画幅比例。",
    type="SingleChoice",
    options=[QuestionOption(**option) for option in SIZE_QUESTION_OPTIONS],
    allow_custom_input=False,
)


async def image_parameters_node(
    state: ImageAgentState,
    config: RunnableConfig | None = None,
) -> dict[str, object]:
    """保留原始商品请求，恢复题卡答案并向共享工具节点发起调用。"""
    configurable = (config or {}).get("configurable", {})
    user_id = configurable.get("user_id")
    conversation_id = configurable.get("conversation_id")
    run_id = configurable.get("run_id")
    if not all(isinstance(value, int) and value > 0 for value in (user_id, conversation_id)):
        raise AgentConfigurationError(
            "图片助手缺少可信用户或会话标识。", code="missing_image_run_identity"
        )
    if not isinstance(run_id, str) or not run_id:
        raise AgentConfigurationError("图片助手缺少运行标识。", code="missing_image_run_id")

    original_request = state.get("original_request", "")
    options = state.get("generation_options") or extract_image_options(original_request)
    resume_answers = configurable.get("resume_answers", {})
    if state.get("awaiting_image_size") and isinstance(resume_answers, dict):
        options = apply_size_answer(options, resume_answers)
    else:
        options = (
            ImageGenerationOptions(**options).validate_exclusivity().model_dump(exclude_none=True)
        )

    task_result_id = state.get("task_result_id") or str(generate_snowflake_id())
    prompt = state.get("image_prompt", "").strip() or original_request
    if not prompt:
        raise AgentExecutionError("没有可用于生成图片的商品描述。", code="empty_image_prompt")

    if "size" not in options and "generate_max_pixels" not in options:
        call = {
            "name": "ask_user_questions",
            "args": {"questions": [SIZE_QUESTION.model_dump(mode="json")]},
            "id": uuid.uuid4().hex,
            "type": "tool_call",
        }
        return {
            "messages": [AIMessage(content="", tool_calls=[call])],
            "original_request": original_request,
            "image_prompt": prompt,
            "generation_options": options,
            "task_result_id": task_result_id,
            "awaiting_image_size": True,
        }

    call = {
        "name": "generate_image",
        "args": {
            "task_result_id": task_result_id,
            "user_id": user_id,
            "conversation_id": conversation_id,
            "prompt": prompt,
            **options,
        },
        "id": uuid.uuid4().hex,
        "type": "tool_call",
    }
    return {
        "messages": [AIMessage(content="", tool_calls=[call])],
        "original_request": original_request,
        "image_prompt": prompt,
        "generation_options": options,
        "task_result_id": task_result_id,
        "awaiting_image_size": False,
    }
