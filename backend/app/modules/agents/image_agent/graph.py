"""组装共享输入/题卡/工具节点和图片助手专属处理节点。"""

from typing import Any, Literal

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.constants import END, START
from langgraph.graph import StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agent.config import BaseAgentConfig
from app.agent.errors import AgentExecutionError
from app.agent.nodes.input import create_input_node
from app.agent.nodes.output import output_node
from app.agent.nodes.tool import _is_question_message, create_tool_node
from app.agent.tools.builtin.ask_user_questions import ask_user_questions
from app.agent.tools.registry import ToolRegistry
from app.modules.agents.image_agent.constants import IMAGE_AGENT_CODE
from app.modules.agents.image_agent.nodes.request import create_request_node, route_after_request
from app.modules.agents.image_agent.nodes.result import image_result_node
from app.modules.agents.image_agent.prompts.loader import load_image_agent_prompt
from app.modules.agents.image_agent.state import ImageAgentState


def build_image_agent_graph(
    *,
    chat_model: Any,
    generate_image_tool: Any,
    checkpointer: BaseCheckpointSaver[Any] | None = None,
) -> CompiledStateGraph[Any, Any, Any, Any]:
    """复用 app/agent 现有节点和工具执行器构建图片专属图。"""
    config = BaseAgentConfig(system_prompt=load_image_agent_prompt(), agent=IMAGE_AGENT_CODE)
    registry = ToolRegistry([ask_user_questions, generate_image_tool])
    graph = StateGraph(ImageAgentState)
    graph.add_node("input_node", create_input_node(config))
    graph.add_node("request_node", create_request_node(chat_model, config.system_prompt))
    graph.add_node("tool_node", create_tool_node(registry))
    graph.add_node("result_node", image_result_node)
    graph.add_node("output_node", output_node)
    graph.add_edge(START, "input_node")
    graph.add_edge("input_node", "request_node")
    graph.add_conditional_edges(
        "request_node",
        route_after_request,
        {"tool_node": "tool_node", "output_node": "output_node"},
    )
    graph.add_conditional_edges(
        "tool_node",
        _route_after_tools,
        {"pause": END, "result_node": "result_node"},
    )
    graph.add_edge("result_node", "output_node")
    graph.add_edge("output_node", END)
    return graph.compile(checkpointer=checkpointer)


def _route_after_tools(state: ImageAgentState) -> Literal["pause", "result_node"]:
    messages = state.get("messages", [])
    last_message = messages[-1] if messages else None
    if _is_question_message(last_message):
        return "pause"
    if getattr(last_message, "name", None) != "generate_image":
        raise AgentExecutionError("图片助手工具返回了未知结果。", code="invalid_image_tool_result")
    return "result_node"
