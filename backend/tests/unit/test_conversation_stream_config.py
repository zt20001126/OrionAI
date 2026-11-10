"""验证流式会话向需要用户上下文的 Agent 传递可信配置。"""

from types import SimpleNamespace

from starlette.requests import Request

from app.modules.conversations.dependencies.dependencies import get_request_client_ip
from app.modules.conversations.service.service import ConversationService


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


def test_digital_human_stream_receives_current_request_ip() -> None:
    prepared = SimpleNamespace(
        user_id=42,
        conversation=SimpleNamespace(id=7, skill_code="digital_human"),
        message_id=99,
        resume_answers=None,
        client_ip="114.247.50.2",
    )

    config = ConversationService._runnable_config(prepared, "digital:42:7")

    assert config["configurable"]["client_ip"] == "114.247.50.2"


def test_request_ip_comes_from_asgi_client_not_forwarded_header() -> None:
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/",
            "headers": [(b"x-forwarded-for", b"203.0.113.10")],
            "client": ("114.247.50.2", 50000),
            "server": ("testserver", 80),
            "scheme": "http",
            "query_string": b"",
            "http_version": "1.1",
        }
    )

    assert get_request_client_ip(request) == "114.247.50.2"


def test_concurrent_digital_human_configs_keep_client_ips_separate() -> None:
    first_turn = SimpleNamespace(
        user_id=1,
        conversation=SimpleNamespace(id=10, skill_code="digital_human"),
        message_id=100,
        resume_answers=None,
        client_ip="114.247.50.2",
    )
    second_turn = SimpleNamespace(
        user_id=2,
        conversation=SimpleNamespace(id=20, skill_code="digital_human"),
        message_id=200,
        resume_answers=None,
        client_ip="8.8.8.8",
    )

    first_config = ConversationService._runnable_config(first_turn, "digital:1:10")
    second_config = ConversationService._runnable_config(second_turn, "digital:2:20")

    assert first_config["configurable"]["client_ip"] == "114.247.50.2"
    assert second_config["configurable"]["client_ip"] == "8.8.8.8"
