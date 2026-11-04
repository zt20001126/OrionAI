"""提取评价事实、检索真实规则并校验模型匹配结果。"""

import json
from collections.abc import Callable
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.runnables import RunnableConfig

from app.modules.agents.tourism_insight.prompts.loader import load_prompt
from app.modules.agents.tourism_insight.schemas import (
    FactExtraction,
    MatchCandidate,
    MatchProposalList,
)
from app.modules.agents.tourism_insight.state import TourismInsightState
from app.modules.agents.tourism_insight.tools.search_rules import create_search_rules_tool


def create_analyze_node(chat_model: Any, searcher: Callable[[int, str], list[dict[str, object]]]):
    """创建一个分析节点，局部完成事实、检索和规则匹配。"""
    extraction_model = chat_model.with_structured_output(FactExtraction, method="json_mode")
    match_model = chat_model.with_structured_output(MatchProposalList, method="json_mode")
    prompt = load_prompt("analysis.md")
    extraction_instructions = PydanticOutputParser(
        pydantic_object=FactExtraction
    ).get_format_instructions()
    match_instructions = PydanticOutputParser(
        pydantic_object=MatchProposalList
    ).get_format_instructions()

    async def analyze_node(
        state: TourismInsightState,
        config: RunnableConfig | None = None,
    ) -> dict[str, object]:
        message = next(
            (
                item
                for item in reversed(state.get("messages", []))
                if isinstance(item, HumanMessage)
            ),
            None,
        )
        text = message.content.strip() if message and isinstance(message.content, str) else ""
        facts_result = FactExtraction.model_validate(
            await extraction_model.ainvoke(
                [
                    SystemMessage(content=f"{prompt}\n{extraction_instructions}"),
                    HumanMessage(content=text),
                ]
            )
        )
        configurable = dict((config or {}).get("configurable") or {})
        user_id = configurable.get("user_id")
        if not isinstance(user_id, int) or user_id <= 0:
            raise ValueError("缺少可信用户上下文")
        if not facts_result.facts:
            unmatched = [
                MatchCandidate(rule_id=None, evidence=None, reason=None, status="unmatched")
            ]
            return {
                "analysis_context": {
                    "in_scope": True,
                    "validated_matches": [item.model_dump() for item in unmatched],
                }
            }

        tool = create_search_rules_tool(searcher, user_id)
        candidates_by_id: dict[str, dict[str, object]] = {}
        for fact in facts_result.facts:
            result = await tool.ainvoke({"query": fact.fact})
            if isinstance(result, list):
                for candidate in result:
                    if isinstance(candidate, dict) and isinstance(candidate.get("id"), str):
                        candidates_by_id[candidate["id"]] = candidate

        if not candidates_by_id:
            matches = [
                MatchCandidate(
                    rule_id=None,
                    evidence=facts_result.facts[0].evidence,
                    reason=None,
                    status="unmatched",
                )
            ]
        else:
            prompt_content = {
                "comment": text,
                "facts": [fact.model_dump() for fact in facts_result.facts],
                "candidate_rules": list(candidates_by_id.values()),
            }
            proposal = MatchProposalList.model_validate(
                await match_model.ainvoke(
                    [
                        SystemMessage(content=f"{prompt}\n{match_instructions}"),
                        HumanMessage(content=json.dumps(prompt_content, ensure_ascii=False)),
                    ]
                )
            )
            candidate_ids = set(candidates_by_id)
            matches = []
            for item in proposal.matches:
                if item.rule_id is not None and item.rule_id not in candidate_ids:
                    continue
                if item.evidence and item.evidence not in text:
                    continue
                if item.status == "matched" and (item.rule_id is None or not item.evidence):
                    continue
                if item.status == "review" and (item.rule_id is None or not item.evidence):
                    continue
                if item.status == "unmatched" and item.rule_id is not None:
                    continue
                matches.append(item)
            if not matches:
                matches = [
                    MatchCandidate(
                        rule_id=None,
                        evidence=facts_result.facts[0].evidence,
                        reason=None,
                        status="unmatched",
                    )
                ]

        return {
            "analysis_context": {
                "in_scope": True,
                "validated_matches": [item.model_dump() for item in matches],
            }
        }

    return analyze_node
