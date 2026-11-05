"""定义对话模块可安全返回给 API 调用方的业务异常。"""


class ConversationError(Exception):
    """对话业务错误，包含稳定 HTTP 状态和中文说明。"""

    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


class ConversationNotFoundError(ConversationError):
    """会话不存在或不属于当前用户。"""

    def __init__(self) -> None:
        super().__init__(404, "会话不存在。")


class ConversationConflictError(ConversationError):
    """会话状态不允许当前操作。"""

    def __init__(self, detail: str = "当前会话状态不允许此操作。") -> None:
        super().__init__(409, detail)


class ConversationValidationError(ConversationError):
    """请求内容或题卡答案不符合业务约定。"""

    def __init__(self, detail: str) -> None:
        super().__init__(422, detail)


class ConversationUnavailableError(ConversationError):
    """数据库、Agent 配置或模型暂不可用。"""

    def __init__(self) -> None:
        super().__init__(503, "对话服务暂不可用，请稍后重试。")
