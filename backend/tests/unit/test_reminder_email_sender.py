from __future__ import annotations

import smtplib
from email.message import EmailMessage

import pytest

from app.core.config import Settings
from app.infrastructure.email import email_sender
from app.infrastructure.email.email_sender import EmailDeliveryError


class RecordingSMTP:
    """捕获发送内容并模拟 SMTP 接受，不建立真实网络连接。"""

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        self.message: EmailMessage | None = None

    def __enter__(self) -> RecordingSMTP:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def login(self, _username: str, _password: str) -> None:
        return None

    def send_message(self, message: EmailMessage) -> None:
        self.message = message


def test_generic_email_sender_uses_configured_smtp_and_bodies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """通用 SMTP 接口保留主题、账号发件地址、纯文本和可选 HTML。"""

    smtp = RecordingSMTP()
    monkeypatch.setattr(email_sender.smtplib, "SMTP_SSL", lambda *_args, **_kwargs: smtp)
    settings = Settings(
        smtp_host="smtp.example.com",
        smtp_username="sender@example.com",
        smtp_password="test-password",
        smtp_from_email="sender@example.com",
    )

    email_sender.send_email(
        settings,
        recipient="owner@example.com",
        subject="OrionAI 提醒",
        text_body="提交周报。",
        html_body="<p>提交周报。</p>",
    )

    assert smtp.message is not None
    assert smtp.message["To"] == "owner@example.com"
    assert smtp.message["Subject"] == "OrionAI 提醒"
    assert smtp.message.get_body(preferencelist=("plain",)).get_content().strip() == "提交周报。"
    assert (
        smtp.message.get_body(preferencelist=("html",)).get_content().strip() == "<p>提交周报。</p>"
    )


@pytest.mark.parametrize(("status_code", "retryable"), [(450, True), (550, False)])
def test_smtp_response_errors_are_classified_by_status(
    monkeypatch: pytest.MonkeyPatch,
    status_code: int,
    retryable: bool,
) -> None:
    """SMTP 4xx 响应可重试，5xx 响应作为永久失败处理。"""

    class RejectingSMTP(RecordingSMTP):
        def send_message(self, _message: EmailMessage) -> None:
            raise smtplib.SMTPResponseException(status_code, b"hidden response")

    monkeypatch.setattr(email_sender.smtplib, "SMTP_SSL", lambda *_args, **_kwargs: RejectingSMTP())
    settings = Settings(
        smtp_host="smtp.example.com",
        smtp_username="sender@example.com",
        smtp_password="test-password",
        smtp_from_email="sender@example.com",
    )

    with pytest.raises(EmailDeliveryError) as error:
        email_sender.send_email(
            settings,
            recipient="owner@example.com",
            subject="OrionAI 提醒",
            text_body="提交周报。",
        )

    assert error.value.retryable is retryable
    assert "hidden response" not in str(error.value)
