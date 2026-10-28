"""定义提醒模块可安全映射到 HTTP 响应的业务异常。"""


class ReminderError(RuntimeError):
    """提醒业务异常基类，供应用层统一转换为 detail 响应。"""

    status_code = 503
    detail = "提醒服务暂时不可用，请稍后重试。"

    def __init__(self, detail: str | None = None) -> None:
        self.detail = detail or type(self).detail
        super().__init__(self.detail)


class ReminderNotFoundError(ReminderError):
    """提醒不存在或不属于当前登录用户。"""

    status_code = 404
    detail = "提醒不存在或当前不可用。"


class ReminderConflictError(ReminderError):
    """提醒状态或并发版本不允许执行当前操作。"""

    status_code = 409
    detail = "提醒状态已发生变化，请刷新后重试。"


class ReminderScheduleError(ReminderError):
    """提醒时间、时区或重复规则不合法。"""

    status_code = 422
    detail = "提醒时间或重复规则无效。"


class ReminderUnavailableError(ReminderError):
    """提醒数据库或必要服务暂时不可用。"""

    status_code = 503
    detail = "提醒服务暂时不可用，请稍后重试。"
