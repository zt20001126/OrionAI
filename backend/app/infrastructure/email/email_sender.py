import smtplib
from email.message import EmailMessage
from email.utils import formataddr

from app.core.config import Settings


class EmailDeliveryError(Exception):
    """SMTP 邮件发送错误，并标记是否值得通过定时重试恢复。"""

    def __init__(self, message: str, *, retryable: bool = True) -> None:
        self.retryable = retryable
        super().__init__(message)


def send_auth_code_email(settings: Settings, account: str, code: str, purpose: str) -> None:
    purpose_label = {
        "register": "注册",
        "password_reset": "重置密码",
        "password_change": "修改密码",
    }.get(purpose, "账号验证")
    expiry_label = "5 分钟" if purpose == "password_change" else "10 分钟"
    message = EmailMessage()
    message["Subject"] = f"OrionAI {purpose_label}验证码"
    message["From"] = formataddr((settings.smtp_from_name, settings.smtp_from_email))
    message["To"] = account
    message.set_content(
        f"你的 OrionAI {purpose_label}验证码是：{code}\n"
        f"验证码 {expiry_label}内有效，请勿向他人透露。"
    )
    message.add_alternative(
        "<html><body>"
        f"<p>你的 OrionAI {purpose_label}验证码是：</p>"
        f"<p style='font-size:28px;font-weight:bold;letter-spacing:6px'>{code}</p>"
        f"<p>验证码 {expiry_label}内有效，请勿向他人透露。</p>"
        "</body></html>",
        subtype="html",
    )

    _send_message(settings, message)


def send_email(
    settings: Settings,
    *,
    recipient: str,
    subject: str,
    text_body: str,
    html_body: str | None = None,
) -> None:
    """通过项目 SMTP 配置发送通用文本邮件，可选 HTML 正文。"""

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = formataddr((settings.smtp_from_name, settings.smtp_from_email))
    message["To"] = recipient
    message.set_content(text_body)
    if html_body is not None:
        message.add_alternative(html_body, subtype="html")
    _send_message(settings, message)


def _send_message(settings: Settings, message: EmailMessage) -> None:
    """使用现有 SSL/STARTTLS 选项发送邮件并分类可重试错误。"""

    if not all(
        (
            settings.smtp_host,
            settings.smtp_username,
            settings.smtp_password,
            settings.smtp_from_email,
        )
    ):
        raise EmailDeliveryError("SMTP 尚未完成配置。", retryable=False)

    try:
        if settings.smtp_use_ssl:
            with smtplib.SMTP_SSL(
                settings.smtp_host,
                settings.smtp_port,
                timeout=settings.smtp_timeout_seconds,
            ) as smtp:
                smtp.login(settings.smtp_username, settings.smtp_password)
                smtp.send_message(message)
        else:
            with smtplib.SMTP(
                settings.smtp_host,
                settings.smtp_port,
                timeout=settings.smtp_timeout_seconds,
            ) as smtp:
                smtp.starttls()
                smtp.login(settings.smtp_username, settings.smtp_password)
                smtp.send_message(message)
    except (smtplib.SMTPAuthenticationError, smtplib.SMTPRecipientsRefused) as error:
        raise EmailDeliveryError("SMTP 拒绝了认证或收件地址。", retryable=False) from error
    except smtplib.SMTPResponseException as error:
        raise EmailDeliveryError("SMTP 邮件发送失败。", retryable=error.smtp_code < 500) from error
    except (OSError, smtplib.SMTPException) as error:
        raise EmailDeliveryError("SMTP 邮件发送失败。", retryable=True) from error
