"""为用户会话构造服务端控制的 LangGraph Checkpointer 线程 ID。"""

from app.agent.config import BASIC_CONVERSATION_AGENT


def build_conversation_thread_id(user_id: int, conversation_id: int) -> str:
    """将用户、Agent 和会话 ID 组合为稳定且相互隔离的线程标识。"""

    if user_id <= 0 or conversation_id <= 0:
        raise ValueError("用户 ID 和会话 ID 必须为正整数。")
    return f"orionai:{user_id}:{BASIC_CONVERSATION_AGENT}:{conversation_id}"
