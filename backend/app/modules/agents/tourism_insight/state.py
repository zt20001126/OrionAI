"""定义文旅洞察智能体图节点共享的专属状态。"""

from typing import Annotated, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

from app.modules.agents.tourism_insight.schemas import MatchCandidate


class AnalysisContext(TypedDict, total=False):
    """保存本轮分支状态和经过校验、等待写入的匹配列表。"""

    in_scope: bool
    validated_matches: list[MatchCandidate]


class TourismInsightState(TypedDict, total=False):
    """文旅洞察图状态；业务中间事实在单个节点内处理。"""

    messages: Annotated[list[BaseMessage], add_messages]
    answer: str
    question_round_count: int
    analysis_context: AnalysisContext
