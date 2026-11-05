"""生成需用户确认的邮件草稿，发送由会话服务执行。"""

import json
from uuid import uuid4

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from pydantic import BaseModel, Field, field_validator

from app.agent.schemas import Question, QuestionOption, QuestionPayload
from app.core.config import get_settings
from app.infrastructure.redis.client import create_redis_client
from app.modules.auth.schemas import EmailRequest

DRAFT_TTL_SECONDS = 3600
EMAIL_QUESTION_PREFIX = "email_"
CONFIRM_SEND = "确认发送"


class EmailDraftInput(BaseModel):
    """数字人生成的邮件草稿，不包含可由模型指定的发件人。"""

    recipient: str = Field(description="收件人的邮箱地址")
    subject: str = Field(min_length=1, max_length=100, description="邮件主题")
    body: str = Field(min_length=1, max_length=2200, description="邮件正文")

    @field_validator("recipient")
    @classmethod
    def validate_recipient(cls, value: str) -> str:
        """校验收件地址；输入邮箱字符串，输出规范邮箱；调用方：草稿工具。"""
        return EmailRequest(email=value).email

    @field_validator("subject")
    @classmethod
    def validate_subject(cls, value: str) -> str:
        """限制主题为非空单行文本；调用方：草稿工具。"""
        value = value.strip()
        if not value or any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise ValueError("邮件主题必须是非空单行文本。")
        return value

    @field_validator("body")
    @classmethod
    def validate_body(cls, value: str) -> str:
        """拒绝空正文；调用方：草稿工具。"""
        value = value.strip()
        if not value:
            raise ValueError("邮件正文不能为空。")
        return value


def draft_key(user_id: int, conversation_id: int, question_id: str) -> str:
    """构造与用户、会话及题卡绑定的草稿键；调用方：草稿工具和会话服务。"""
    return f"orionai:email:draft:{user_id}:{conversation_id}:{question_id}"


@tool("prepare_email", args_schema=EmailDraftInput)
def prepare_email(recipient: str, subject: str, body: str, config: RunnableConfig) -> str:
    """准备邮件草稿并展示确认题卡；不能自行发送邮件。"""
    draft = EmailDraftInput(recipient=recipient, subject=subject, body=body)
    context = config["configurable"]
    user_id = int(context["user_id"])
    conversation_id = int(context["conversation_id"])
    question_id = EMAIL_QUESTION_PREFIX + uuid4().hex
    settings = get_settings()
    if not settings.smtp_from_email:
        raise ValueError("项目发件邮箱尚未配置。")
    preview = (
        f"发件人：{settings.smtp_from_email}\n收件人：{draft.recipient}\n"
        f"主题：{draft.subject}\n\n{draft.body}"
    )
    payload = QuestionPayload(
        questions=[
            Question(
                id=question_id,
                title="请确认邮件内容",
                context=preview,
                type="SingleChoice",
                options=[
                    QuestionOption(label=CONFIRM_SEND, description="使用项目邮箱发送以上内容"),
                    QuestionOption(label="取消发送", description="不发送这封邮件"),
                    QuestionOption(label="修改内容", description="取消草稿并重新编辑"),
                    QuestionOption(label="暂不发送", description="取消本次发送"),
                ],
                allow_custom_input=False,
            )
        ]
    )
    client = create_redis_client()
    try:
        client.set(
            draft_key(user_id, conversation_id, question_id),
            json.dumps(
                {
                    "draft": draft.model_dump(),
                    "preview": preview,
                    "sender": settings.smtp_from_email,
                },
                ensure_ascii=False,
            ),
            ex=DRAFT_TTL_SECONDS,
        )
    finally:
        client.close()
    return payload.model_dump_json()
