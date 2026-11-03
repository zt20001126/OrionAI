"""定义数字人 LangGraph 图自己的可持久化会话状态。"""

from typing import Annotated, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class DigitalHumanState(TypedDict, total=False):
    """数字人每轮使用消息历史和最终文本，结构与共享 Checkpointer 兼容。"""

    messages: Annotated[list[BaseMessage], add_messages]
    answer: str
