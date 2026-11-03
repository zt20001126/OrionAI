"""构造数字人模块独立的输入、模型和输出 LangGraph。"""

from langchain_core.language_models import BaseChatModel
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.constants import END, START
from langgraph.graph import StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agent.config import BaseAgentConfig
from app.agent.nodes.input import create_input_node
from app.agent.nodes.model import create_agent_node
from app.agent.nodes.output import output_node
from app.agent.tools.registry import ToolRegistry
from app.modules.digital_human.agent.prompts.loader import load_digital_human_prompt
from app.modules.digital_human.agent.state import DigitalHumanState

DIGITAL_HUMAN_AGENT_CODE = "digital_human"
MAX_INPUT_CHARS = 20_000
RECURSION_LIMIT = 24


def create_digital_human_graph(
    *,
    chat_model: BaseChatModel,
    checkpointer: BaseCheckpointSaver[object] | None = None,
) -> CompiledStateGraph[DigitalHumanState, object, object, object]:
    """用数字人专属身份和无工具执行流程编译独立图。"""

    config = BaseAgentConfig(
        system_prompt=load_digital_human_prompt(),
        agent=DIGITAL_HUMAN_AGENT_CODE,
        max_input_chars=MAX_INPUT_CHARS,
        recursion_limit=RECURSION_LIMIT,
    )
    graph = StateGraph(DigitalHumanState)
    graph.add_node("input_node", create_input_node(config))
    graph.add_node(
        "agent_node",
        create_agent_node(
            config=config,
            chat_model=chat_model,
            tool_registry=ToolRegistry(),
        ),
    )
    graph.add_node("output_node", output_node)
    graph.add_edge(START, "input_node")
    graph.add_edge("input_node", "agent_node")
    graph.add_edge("agent_node", "output_node")
    graph.add_edge("output_node", END)
    return graph.compile(checkpointer=checkpointer)
