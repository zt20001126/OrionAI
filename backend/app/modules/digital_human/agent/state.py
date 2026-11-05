"""定义数字人 LangGraph 图自己的可持久化会话状态。"""

from typing import Annotated, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class DigitalHumanState(TypedDict, total=False):
    """保存数字人图的消息、最终文本和题卡轮数，兼容共享 Checkpointer。"""

    messages: Annotated[list[BaseMessage], add_messages]
    answer: str
    question_round_count: int
