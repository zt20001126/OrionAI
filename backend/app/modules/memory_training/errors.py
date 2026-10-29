"""定义记忆训练模块可映射为安全 HTTP 响应的业务异常。"""


class MemoryTrainingError(RuntimeError):
    """携带稳定状态码、业务码和用户可见文案的模块异常。"""

    status_code = 503
    code = "MEMORY_TRAINING_UNAVAILABLE"
    detail = "记忆训练服务暂时不可用，请稍后重试。"

    def __init__(
        self,
        detail: str | None = None,
        *,
        code: str | None = None,
        status_code: int | None = None,
    ) -> None:
        self.detail = detail or type(self).detail
        self.code = code or type(self).code
        self.status_code = status_code or type(self).status_code
        super().__init__(self.detail)


class MemoryTrainingNotFoundError(MemoryTrainingError):
    """训练会话不存在、已过期或不属于当前用户。"""

    status_code = 404
    code = "MEMORY_TRAINING_SESSION_NOT_FOUND"
    detail = "训练会话不存在或当前不可用。"


class MemoryTrainingConflictError(MemoryTrainingError):
    """训练会话当前状态不允许执行请求操作。"""

    status_code = 409
    code = "MEMORY_TRAINING_STATE_CONFLICT"
    detail = "训练状态已变化，请刷新后重试。"


class MemoryTrainingValidationError(MemoryTrainingError):
    """用户提交的答案不完整或不属于当前题目。"""

    status_code = 422
    code = "MEMORY_TRAINING_ANSWERS_INVALID"
    detail = "答案无效，请检查每道题的选项后重试。"


class MemoryTrainingUnavailableError(MemoryTrainingError):
    """PostgreSQL、Redis、模型或 OSS 等必要依赖暂时不可用。"""

    status_code = 503
    code = "MEMORY_TRAINING_UNAVAILABLE"
    detail = "记忆训练服务暂时不可用，请稍后重试。"
