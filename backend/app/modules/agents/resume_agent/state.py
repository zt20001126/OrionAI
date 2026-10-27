"""简历助手图状态。"""

from typing import Any

from app.agent.state import ConversationState


class ResumeAgentState(ConversationState, total=False):
    pending_resume_optimization: dict[str, Any] | None
    direct_resume_answer: bool
