"""定义反馈模块可预期的限流、基础设施和邮件投递错误。"""


class FeedbackRateLimitError(Exception):
    """当前用户在限流窗口内已提交过反馈。"""


class FeedbackUnavailableError(Exception):
    """反馈依赖的限流或邮件基础设施暂不可用。"""


class FeedbackDeliveryError(Exception):
    """反馈邮件未能由 SMTP 服务器接受。"""
