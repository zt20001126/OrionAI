"""判断当前轮输入是否属于文旅评价业务范围。"""

from collections.abc import Callable
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.modules.agents.tourism_insight.prompts.loader import load_prompt
from app.modules.agents.tourism_insight.schemas import ScopeDecision
from app.modules.agents.tourism_insight.state import TourismInsightState

OUT_OF_SCOPE_REPLY = (
    "我是文旅洞察智能体，只能分析游客评论并匹配景区评分规则。"
    "请发送一段游客评价，例如：景区指引清晰，但卫生间排队较久。"
)


def create_scope_node(chat_model: Any) -> Callable[..., Any]:
    """创建业务范围节点；无关输入直接产生引导回复。"""
    model = chat_model.with_structured_output(ScopeDecision, method="json_mode")
    system_prompt = load_prompt("system.md")

    async def scope_node(state: TourismInsightState) -> dict[str, object]:
        message = next(
            (
                item
                for item in reversed(state.get("messages", []))
                if isinstance(item, HumanMessage)
            ),
            None,
        )
        text = message.content.strip() if message and isinstance(message.content, str) else ""
        decision = await model.ainvoke(
            [SystemMessage(content=system_prompt), HumanMessage(content=text)]
        )
        in_scope = ScopeDecision.model_validate(decision).in_scope
        context: dict[str, object] = {"in_scope": in_scope, "validated_matches": []}
        if not in_scope:
            return {
                "analysis_context": context,
                "messages": [AIMessage(content=OUT_OF_SCOPE_REPLY)],
            }
        return {"analysis_context": context}

    return scope_node
