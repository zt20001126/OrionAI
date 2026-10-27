"""为用户会话构造服务端控制的 LangGraph Checkpointer 线程 ID。"""

from app.agent.config import BASIC_CONVERSATION_AGENT


def build_conversation_thread_id(
    user_id: int,
    conversation_id: int,
    skill_code: str = "general_chat",
) -> str:
    """将用户、Agent 和会话 ID 组合为稳定且相互隔离的线程标识。"""

    if user_id <= 0 or conversation_id <= 0:
        raise ValueError("用户 ID 和会话 ID 必须为正整数。")
    if not skill_code or ":" in skill_code:
        raise ValueError("技能代码不能为空或包含冒号。")
    agent_name = BASIC_CONVERSATION_AGENT if skill_code == "general_chat" else skill_code
    return f"orionai:{user_id}:{agent_name}:{conversation_id}"
