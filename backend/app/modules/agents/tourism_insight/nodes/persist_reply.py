"""最终复核当前规则归属、保存分析结果并生成面向用户的答复。"""

from collections.abc import Callable

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig

from app.modules.agents.tourism_insight.schemas import MatchCandidate
from app.modules.agents.tourism_insight.state import TourismInsightState


def create_persist_reply_node(
    saver: Callable[[int, str, str | None, list[dict[str, object]]], int],
):
    """构造持久化节点；只有前序范围判断通过才会执行此节点。"""

    async def persist_reply_node(
        state: TourismInsightState,
        config: RunnableConfig | None = None,
    ) -> dict[str, object]:
        configurable = dict((config or {}).get("configurable") or {})
        user_id = configurable.get("user_id")
        if not isinstance(user_id, int) or user_id <= 0:
            raise ValueError("缺少可信用户上下文")
        message = next(
            (
                item
                for item in reversed(state.get("messages", []))
                if isinstance(item, HumanMessage)
            ),
            None,
        )
        text = message.content.strip() if message and isinstance(message.content, str) else ""
        context = state.get("analysis_context", {})
        matches = [
            MatchCandidate.model_validate(item) for item in context.get("validated_matches", [])
        ]
        source_comment_id = configurable.get("source_comment_id")
        saver(
            user_id,
            text,
            str(source_comment_id) if source_comment_id is not None else None,
            [item.model_dump() for item in matches],
        )
        matched_count = sum(item.status == "matched" for item in matches)
        review_count = sum(item.status == "review" for item in matches)
        if matched_count:
            answer = (
                f"已完成评论分析，找到 {matched_count} 个评分子项匹配。"
                "完整指标层级、原文证据和匹配依据可在「分析结果」中查看。"
            )
        elif review_count:
            answer = "已完成初步分析，部分内容需要人工核验。请在「分析结果」中查看证据和判断依据。"
        else:
            answer = "未找到证据充分的评分子项匹配。评论已保存，可在「分析结果」中查看并复查。"
        return {
            "messages": [AIMessage(content=answer)],
            "answer": answer,
            "analysis_context": {"in_scope": True, "validated_matches": []},
        }

    return persist_reply_node
