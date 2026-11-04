"""验证文旅分析结果中的段落情感字段和候选校验。"""

from collections.abc import Sequence
from typing import Any

import pytest
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, ValidationError

from app.modules.agents.tourism_insight.nodes.analyze import create_analyze_node
from app.modules.agents.tourism_insight.schemas import (
    FactExtraction,
    MatchCandidate,
    MatchProposalList,
)


class _ScriptedStructuredModel:
    """按输出 Schema 返回预设结果，隔离真实模型调用。"""

    def __init__(self, responses: Sequence[object]) -> None:
        self._responses = list(responses)
        self.received_messages: list[list[object]] = []

    async def ainvoke(self, messages: list[object]) -> object:
        self.received_messages.append(messages)
        return self._responses.pop(0)


class _ScriptedChatModel:
    """为分析节点按结构化输出类型提供预设模型结果。"""

    def __init__(self, responses: dict[type[BaseModel], list[object]]) -> None:
        self._responses = responses
        self.structured_models: dict[type[BaseModel], _ScriptedStructuredModel] = {}

    def with_structured_output(
        self, schema: type[BaseModel], **_kwargs: Any
    ) -> _ScriptedStructuredModel:
        model = _ScriptedStructuredModel(self._responses[schema])
        self.structured_models[schema] = model
        return model


def _fact_extraction(evidence: str = "大厅指引清晰") -> dict[str, object]:
    return {"facts": [{"fact": "大厅指引清晰", "evidence": evidence}]}


def _candidate(
    *,
    sentiment: str = "positive",
    status: str = "matched",
    rule_id: str | None = "rule-1",
    evidence: str | None = "大厅指引清晰",
) -> dict[str, object]:
    return {
        "rule_id": rule_id,
        "evidence": evidence,
        "reason": "评论明确描述指引清晰",
        "status": status,
        "sentiment": sentiment,
    }


@pytest.mark.anyio
async def test_analyze_node_preserves_sentiment_on_valid_match() -> None:
    model = _ScriptedChatModel(
        {
            FactExtraction: [_fact_extraction()],
            MatchProposalList: [{"matches": [_candidate()]}],
        }
    )
    node = create_analyze_node(model, lambda _user_id, _query: [{"id": "rule-1"}])

    result = await node(
        {"messages": [HumanMessage(content="大厅指引清晰")]},
        {"configurable": {"user_id": 23}},
    )

    assert result["analysis_context"]["validated_matches"] == [_candidate()]
    assert model.structured_models[MatchProposalList].received_messages


@pytest.mark.anyio
async def test_analyze_node_requests_sentiment_when_no_rule_candidates_exist() -> None:
    model = _ScriptedChatModel(
        {
            FactExtraction: [_fact_extraction()],
            MatchProposalList: [
                {
                    "matches": [
                        _candidate(
                            sentiment="objective",
                            status="unmatched",
                            rule_id=None,
                        )
                    ]
                }
            ],
        }
    )
    node = create_analyze_node(model, lambda _user_id, _query: [])

    result = await node(
        {"messages": [HumanMessage(content="大厅指引清晰")]},
        {"configurable": {"user_id": 23}},
    )

    assert result["analysis_context"]["validated_matches"] == [
        _candidate(sentiment="objective", status="unmatched", rule_id=None)
    ]
    messages = model.structured_models[MatchProposalList].received_messages[0]
    assert isinstance(messages[0], SystemMessage)


@pytest.mark.anyio
async def test_analyze_node_keeps_empty_fact_fallback_without_sentiment() -> None:
    model = _ScriptedChatModel({FactExtraction: [{"facts": []}], MatchProposalList: []})
    node = create_analyze_node(model, lambda _user_id, _query: [])

    result = await node(
        {"messages": [HumanMessage(content="没有可拆分事实")]},
        {"configurable": {"user_id": 23}},
    )

    match = result["analysis_context"]["validated_matches"][0]
    assert match["status"] == "unmatched"
    assert match["sentiment"] is None
    assert model.structured_models[MatchProposalList].received_messages == []


def test_match_candidate_rejects_unknown_sentiment() -> None:
    with pytest.raises(ValidationError):
        MatchCandidate.model_validate(_candidate(sentiment="mixed"))


def test_match_candidate_requires_sentiment_field() -> None:
    candidate = _candidate()
    candidate.pop("sentiment")

    with pytest.raises(ValidationError):
        MatchCandidate.model_validate(candidate)
