import smtplib
from email.message import EmailMessage
from email.utils import formataddr

from app.core.config import Settings


class EmailDeliveryError(Exception):
    pass


def send_auth_code_email(settings: Settings, account: str, code: str, purpose: str) -> None:
    if not all(
        (
            settings.smtp_host,
            settings.smtp_username,
            settings.smtp_password,
            settings.smtp_from_email,
        )
    ):
        raise EmailDeliveryError("SMTP 尚未完成配置。")

    purpose_label = "注册" if purpose == "register" else "重置密码"
    message = EmailMessage()
    message["Subject"] = f"OrionAI {purpose_label}验证码"
    message["From"] = formataddr((settings.smtp_from_name, settings.smtp_from_email))
    message["To"] = account
    message.set_content(
        f"你的 OrionAI {purpose_label}验证码是：{code}\n验证码 10 分钟内有效，请勿向他人透露。"
    )
    message.add_alternative(
        "<html><body>"
        f"<p>你的 OrionAI {purpose_label}验证码是：</p>"
        f"<p style='font-size:28px;font-weight:bold;letter-spacing:6px'>{code}</p>"
        "<p>验证码 10 分钟内有效，请勿向他人透露。</p>"
        "</body></html>",
        subtype="html",
    )

    try:
        if settings.smtp_use_ssl:
            with smtplib.SMTP_SSL(
                settings.smtp_host,
                settings.smtp_port,
                timeout=10,
            ) as smtp:
                smtp.login(settings.smtp_username, settings.smtp_password)
                smtp.send_message(message)
        else:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
                smtp.starttls()
                smtp.login(settings.smtp_username, settings.smtp_password)
                smtp.send_message(message)
    except (OSError, smtplib.SMTPException) as error:
        raise EmailDeliveryError("SMTP 邮件发送失败。") from error
