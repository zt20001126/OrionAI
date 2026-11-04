"""验证流式会话向需要用户上下文的 Agent 传递可信配置。"""

from types import SimpleNamespace

from app.modules.conversations.service import ConversationService


def test_tourism_insight_stream_receives_user_context() -> None:
    prepared = SimpleNamespace(
        user_id=42,
        conversation=SimpleNamespace(id=7, skill_code="tourism_insight"),
        message_id=99,
        resume_answers=None,
    )

    config = ConversationService._runnable_config(prepared, "tourism:42:7")

    assert config["configurable"] == {
        "thread_id": "tourism:42:7",
        "user_id": 42,
        "conversation_id": 7,
        "run_id": "99",
    }
