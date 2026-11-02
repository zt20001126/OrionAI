"""定义会员模块可安全返回给 API 调用方的业务异常。"""


class MembershipError(Exception):
    """会员业务错误，携带稳定的 HTTP 状态码和中文说明。"""

    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


class MembershipNotFoundError(MembershipError):
    """套餐、订单或会员记录不存在，或不属于当前用户。"""

    def __init__(self, detail: str = "会员记录不存在。") -> None:
        super().__init__(404, detail)


class MembershipConflictError(MembershipError):
    """订单幂等键冲突或订单当前状态不允许此操作。"""

    def __init__(self, detail: str) -> None:
        super().__init__(409, detail)


class MembershipUnavailableError(MembershipError):
    """会员数据服务暂不可用。"""

    def __init__(self) -> None:
        super().__init__(503, "会员服务暂时不可用，请稍后重试。")
