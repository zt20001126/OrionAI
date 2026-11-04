"""定义文旅智能体结构化模型输出和已校验匹配数据。"""

from typing import Literal

from pydantic import BaseModel, Field


class ScopeDecision(BaseModel):
    """判断当前输入是否属于游客评价和景区服务分析业务。"""

    in_scope: bool = Field(description="输入是否属于文旅评价分析业务")


class ReviewFact(BaseModel):
    """从游客评价中提取的单个独立体验事实。"""

    fact: str = Field(description="对评价事实的简短概括")
    evidence: str = Field(description="逐字摘录的评论原文证据")


class FactExtraction(BaseModel):
    """本轮评价中可用于评分规则匹配的事实列表。"""

    facts: list[ReviewFact] = Field(description="评价事实列表；没有明确事实时为空")


class MatchCandidate(BaseModel):
    """单条评论证据与评分规则的匹配候选。"""

    rule_id: str | None = Field(description="候选规则 ID；未匹配时为空")
    evidence: str | None = Field(description="评论原文证据片段")
    reason: str | None = Field(description="匹配依据")
    status: Literal["matched", "review", "unmatched"] = Field(description="匹配状态")


class MatchProposalList(BaseModel):
    """模型针对当前评价给出的匹配列表。"""

    matches: list[MatchCandidate] = Field(description="可以为空；多个事实可匹配多个评分子项")
