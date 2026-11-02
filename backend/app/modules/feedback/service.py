"""组织问题反馈内容、限流和 SMTP 邮件投递流程。"""

import logging
from datetime import datetime
from uuid import uuid4

from redis import Redis
from redis.exceptions import RedisError

from app.core.config import Settings
from app.infrastructure.email.email_sender import EmailDeliveryError, send_email
from app.modules.auth.models import User
from app.modules.feedback.constants import (
    FEEDBACK_RATE_LIMIT_KEY_PREFIX,
    FEEDBACK_RATE_LIMIT_SECONDS,
    FEEDBACK_TIMEZONE,
    RELEASE_FEEDBACK_LIMIT_SCRIPT,
)
from app.modules.feedback.errors import (
    FeedbackDeliveryError,
    FeedbackRateLimitError,
    FeedbackUnavailableError,
)
from app.modules.feedback.schemas import FeedbackRequest, FeedbackResponse

logger = logging.getLogger(__name__)


class FeedbackService:
    """反馈服务，负责验证限流状态并将用户反馈同步投递到 SMTP。"""

    def __init__(self, redis_client: Redis, settings: Settings) -> None:
        self._redis = redis_client
        self._settings = settings

    def submit_feedback(self, user: User, payload: FeedbackRequest) -> FeedbackResponse:
        """提交反馈邮件。

        Step 1: 以当前用户 ID 原子占用 60 秒限流窗口。
        Step 2: 生成带项目时区的纯文本邮件并发送到现有发件邮箱。
        Step 3: 邮件失败时仅释放本次占用，允许用户重新提交。
        """

        limit_key = f"{FEEDBACK_RATE_LIMIT_KEY_PREFIX}:{user.id}"
        limit_token = uuid4().hex
        try:
            reserved = self._redis.set(
                limit_key,
                limit_token,
                ex=FEEDBACK_RATE_LIMIT_SECONDS,
                nx=True,
            )
        except RedisError as error:
            logger.error("feedback_rate_limit_unavailable user_id=%s", user.id)
            raise FeedbackUnavailableError from error
        if not reserved:
            raise FeedbackRateLimitError

        try:
            submitted_at = datetime.now(FEEDBACK_TIMEZONE).strftime("%Y-%m-%d %H:%M:%S %Z")
            subject = f"[OrionAI 问题反馈] {payload.title}"
            text_body = _build_feedback_body(user, payload, submitted_at)
            # 现有 SMTP 服务的生效发件地址同时作为反馈收件地址。
            send_email(
                self._settings,
                recipient=self._settings.smtp_from_email,
                subject=subject,
                text_body=text_body,
            )
        except EmailDeliveryError as error:
            self._release_limit(limit_key, limit_token, user.id)
            logger.warning(
                "feedback_email_delivery_failed user_id=%s retryable=%s",
                user.id,
                error.retryable,
            )
            raise FeedbackDeliveryError from error
        except Exception as error:
            self._release_limit(limit_key, limit_token, user.id)
            logger.error(
                "feedback_email_unexpected_failure user_id=%s error_type=%s",
                user.id,
                type(error).__name__,
            )
            raise FeedbackDeliveryError from error

        return FeedbackResponse(message="反馈提交成功")

    def _release_limit(self, key: str, token: str, user_id: int) -> None:
        """仅删除与本次请求令牌相同的 Redis 限流键。"""

        try:
            self._redis.eval(RELEASE_FEEDBACK_LIMIT_SCRIPT, 1, key, token)
        except RedisError:
            # 即使 Redis 暂时不可用，也保留原 SMTP 错误并避免记录敏感配置。
            logger.warning("feedback_rate_limit_release_failed user_id=%s", user_id)


def _build_feedback_body(user: User, payload: FeedbackRequest, submitted_at: str) -> str:
    """以纯文本呈现用户身份和反馈，避免将用户输入解释为 HTML。"""

    nickname = user.nickname.strip() if user.nickname and user.nickname.strip() else "未设置"
    account = user.account or "未绑定邮箱"
    return (
        "OrionAI 用户问题反馈\n\n"
        "用户信息\n"
        "--------------------\n"
        f"用户 ID：{user.id}\n"
        f"用户昵称：{nickname}\n"
        f"用户邮箱：{account}\n"
        f"提交时间：{submitted_at}\n\n"
        "反馈标题\n"
        "--------------------\n"
        f"{payload.title}\n\n"
        "反馈内容\n"
        "--------------------\n"
        f"{payload.content}\n"
    )
