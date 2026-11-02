"""验证问题反馈认证、校验、限流和 SMTP 投递流程。"""

import time
from typing import Any, Self

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.infrastructure.email.email_sender import EmailDeliveryError
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.feedback.dependencies import get_feedback_service
from app.modules.feedback.router import router as feedback_router
from app.modules.feedback.service import FeedbackService


class InMemoryFeedbackLimiter:
    """模拟 Redis SET NX 和令牌比较删除，不连接外部服务。"""

    def __init__(self) -> None:
        self._entries: dict[str, tuple[str, float]] = {}

    def set(self, key: str, value: str, *, ex: int, nx: bool) -> bool | None:
        current = self._entries.get(key)
        if current is not None and current[1] > time.monotonic() and nx:
            return None
        self._entries[key] = (value, time.monotonic() + ex)
        return True

    def eval(self, _script: str, _key_count: int, key: str, token: str) -> int:
        current = self._entries.get(key)
        if current is not None and current[0] == token:
            del self._entries[key]
            return 1
        return 0

    def has_key(self, key: str) -> bool:
        current = self._entries.get(key)
        return current is not None and current[1] > time.monotonic()


@pytest.fixture
def feedback_client(monkeypatch: pytest.MonkeyPatch) -> Any:
    """创建隔离的反馈路由、内存限流器和本地 SMTP 假件。"""

    from app.infrastructure.email import email_sender

    user = User(
        id=123,
        account="feedback-owner@example.com",
        password_hash="hash",
        nickname="反馈用户",
    )

    state: dict[str, Any] = {
        "user": user,
        "authenticated": True,
        "limiter": InMemoryFeedbackLimiter(),
        "messages": [],
        "smtp_config": None,
    }
    settings = Settings(
        _env_file=None,
        environment="test",
        auth_cookie_secure=False,
        smtp_host="smtp.example.com",
        smtp_port=465,
        smtp_username="smtp-login@example.com",
        smtp_password="test-secret",
        smtp_from_email="feedback@example.com",
        smtp_from_name="OrionAI",
        smtp_use_ssl=True,
    )
    test_app = FastAPI()
    test_app.include_router(feedback_router, prefix="/api")

    def override_current_user() -> User:
        if not state["authenticated"]:
            raise HTTPException(status_code=401, detail="请先登录。")
        return state["user"]

    def override_feedback_service() -> FeedbackService:
        return FeedbackService(state["limiter"], settings)

    class FakeSMTP:
        def __init__(self, host: str, port: int, *, timeout: float) -> None:
            state["smtp_config"] = (host, port, timeout)

        def __enter__(self) -> Self:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def login(self, username: str, password: str) -> None:
            assert username == settings.smtp_username
            assert password == settings.smtp_password

        def send_message(self, message: object) -> None:
            state["messages"].append(message)

    monkeypatch.setattr(email_sender.smtplib, "SMTP_SSL", FakeSMTP)
    test_app.dependency_overrides[get_current_user] = override_current_user
    test_app.dependency_overrides[get_feedback_service] = override_feedback_service
    try:
        with TestClient(test_app) as client:
            yield client, state
    finally:
        test_app.dependency_overrides.clear()


def test_authenticated_user_submits_feedback_and_sender_matches_recipient(
    feedback_client: tuple[TestClient, dict[str, Any]],
) -> None:
    client, state = feedback_client

    response = client.post(
        "/api/v1/feedback",
        json={"title": "图片助手生成失败", "content": "提交后没有返回结果。\n复现步骤：再次提交。"},
    )

    assert response.status_code == 200
    assert response.json() == {"message": "反馈提交成功"}
    assert len(state["messages"]) == 1
    message = state["messages"][0]
    assert message["Subject"] == "[OrionAI 问题反馈] 图片助手生成失败"
    assert message["From"] == "OrionAI <feedback@example.com>"
    assert message["To"] == "feedback@example.com"
    body = message.get_content()
    assert f"用户 ID：{state['user'].id}" in body
    assert "用户昵称：反馈用户" in body
    assert "用户邮箱：feedback-owner@example.com" in body
    assert "提交时间：" in body
    assert "复现步骤：再次提交。" in body
    assert state["smtp_config"] == ("smtp.example.com", 465, 10.0)


def test_feedback_requires_authenticated_user(
    feedback_client: tuple[TestClient, dict[str, Any]],
) -> None:
    client, state = feedback_client
    state["authenticated"] = False

    response = client.post("/api/v1/feedback", json={"title": "标题", "content": "内容"})

    assert response.status_code == 401
    assert state["messages"] == []


@pytest.mark.parametrize(
    ("payload", "case"),
    [
        ({"title": "", "content": "内容"}, "empty title"),
        ({"title": "标题", "content": ""}, "empty content"),
        ({"title": "标题" * 51, "content": "内容"}, "long title"),
        ({"title": "标题", "content": "内" * 2001}, "long content"),
        ({"title": "   ", "content": "有效内容"}, "blank title"),
        ({"title": "有效标题", "content": " \n  "}, "blank content"),
        ({"title": "第一行\nBcc: attacker@example.com", "content": "内容"}, "header injection"),
    ],
)
def test_feedback_rejects_invalid_input(
    feedback_client: tuple[TestClient, dict[str, Any]],
    payload: dict[str, str],
    case: str,
) -> None:
    client, state = feedback_client

    response = client.post("/api/v1/feedback", json=payload)

    assert response.status_code == 422, case
    assert state["messages"] == []


def test_smtp_failure_returns_service_error_and_releases_rate_limit(
    feedback_client: tuple[TestClient, dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.modules.feedback import service as feedback_service_module

    client, state = feedback_client
    original_send_email = feedback_service_module.send_email

    def fail_sending(*_args: object, **_kwargs: object) -> None:
        raise EmailDeliveryError("SMTP 邮件发送失败。")

    monkeypatch.setattr(feedback_service_module, "send_email", fail_sending)
    payload = {"title": "无法发送", "content": "暂时没有送达。"}

    failed_response = client.post("/api/v1/feedback", json=payload)

    assert failed_response.status_code == 503
    assert failed_response.json() == {"detail": "反馈提交失败，请稍后重试。"}
    assert state["messages"] == []
    assert not state["limiter"].has_key(f"orionai:feedback:rate:user:{state['user'].id}")

    monkeypatch.setattr(feedback_service_module, "send_email", original_send_email)
    retry_response = client.post("/api/v1/feedback", json=payload)
    assert retry_response.status_code == 200


def test_second_feedback_within_sixty_seconds_is_rate_limited(
    feedback_client: tuple[TestClient, dict[str, Any]],
) -> None:
    client, state = feedback_client
    payload = {"title": "重复反馈", "content": "请不要重复发送。"}

    first_response = client.post("/api/v1/feedback", json=payload)
    second_response = client.post("/api/v1/feedback", json=payload)

    assert first_response.status_code == 200
    assert second_response.status_code == 429
    assert len(state["messages"]) == 1
