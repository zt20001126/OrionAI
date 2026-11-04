"""组装文旅洞察智能体专属 LangGraph。"""

from collections.abc import Callable
from typing import Any, Literal

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.constants import END, START
from langgraph.graph import StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agent.config import BaseAgentConfig
from app.agent.nodes.input import create_input_node
from app.agent.nodes.output import output_node
from app.modules.agents.tourism_insight.nodes.analyze import create_analyze_node
from app.modules.agents.tourism_insight.nodes.persist_reply import create_persist_reply_node
from app.modules.agents.tourism_insight.nodes.scope import create_scope_node
from app.modules.agents.tourism_insight.state import TourismInsightState

TOURISM_INSIGHT_CODE = "tourism_insight"
SYSTEM_PROMPT = "你是文旅洞察智能体，请判断当前输入是否属于游客评论和景区服务体验分析。"


def build_tourism_insight_graph(
    *,
    chat_model: Any,
    rule_searcher: Callable[[int, str], list[dict[str, object]]],
    result_saver: Callable[[int, str, str | None, list[dict[str, object]]], int],
    checkpointer: BaseCheckpointSaver[Any] | None,
) -> CompiledStateGraph[Any, Any, Any, Any]:
    """构造本 Agent 自有状态图，复用基础文本输入输出节点。"""
    graph = StateGraph(TourismInsightState)
    graph.add_node(
        "input_node",
        create_input_node(BaseAgentConfig(system_prompt=SYSTEM_PROMPT, agent=TOURISM_INSIGHT_CODE)),
    )
    graph.add_node("scope_node", create_scope_node(chat_model))
    graph.add_node("analyze_node", create_analyze_node(chat_model, rule_searcher))
    graph.add_node("persist_reply_node", create_persist_reply_node(result_saver))
    graph.add_node("output_node", output_node)
    graph.add_edge(START, "input_node")
    graph.add_edge("input_node", "scope_node")
    graph.add_conditional_edges(
        "scope_node", route_after_scope, {"analyze": "analyze_node", "output": "output_node"}
    )
    graph.add_edge("analyze_node", "persist_reply_node")
    graph.add_edge("persist_reply_node", "output_node")
    graph.add_edge("output_node", END)
    return graph.compile(checkpointer=checkpointer)


def route_after_scope(state: TourismInsightState) -> Literal["analyze", "output"]:
    return "analyze" if state.get("analysis_context", {}).get("in_scope") else "output"
