"""判断用户图片意图并整理提示词。"""

from pathlib import Path
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from app.agent.errors import AgentExecutionError
from app.modules.agents.image_agent.schemas import ImageRequestAnalysis
from app.modules.agents.image_agent.state import ImageAgentState

_SYSTEM_PROMPT = (
    Path(__file__).parents[1].joinpath("prompts", "system.md").read_text(encoding="utf-8")
)
OTHER_REQUEST_REPLY = (
    "我是图片助手，可以根据文字帮你生成商品主图或详情页图片。请告诉我商品信息和希望的画面效果。"
)


def create_classification_node(chat_model: Any):
    """从模型结构化输出中提取明确生图意图和提示词。"""
    structured_model = chat_model.with_structured_output(ImageRequestAnalysis)

    async def classify(
        state: ImageAgentState,
        config: RunnableConfig | None = None,
    ) -> dict[str, object]:
        configurable = (config or {}).get("configurable", {})
        resume_answers = configurable.get("resume_answers", {})
        if state.get("awaiting_image_size") and resume_answers:
            return {}
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
        try:
            analysis = await structured_model.ainvoke(
                [SystemMessage(content=_SYSTEM_PROMPT), HumanMessage(content=message.content)]
            )
            result = ImageRequestAnalysis.model_validate(analysis)
        except Exception:
            raise AgentExecutionError(
                "图片助手暂时无法理解本次请求。", code="image_request_analysis_failed"
            ) from None
        return {
            "original_request": message.content.strip()[:20_000],
            "is_image_generation": result.intent == "generate_image",
            "image_prompt": result.image_prompt.strip()[:8_000],
            "generation_options": {},
            "awaiting_image_size": False,
        }

    return classify
