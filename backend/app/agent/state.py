"""定义 LangGraph 节点间传递的消息及题卡轮次状态。"""

from typing import Annotated, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class ConversationState(TypedDict, total=False):
    """保存可序列化的对话消息、最终文本和当前运行题卡轮数。"""

    messages: Annotated[list[BaseMessage], add_messages]
    answer: str
    question_round_count: int
