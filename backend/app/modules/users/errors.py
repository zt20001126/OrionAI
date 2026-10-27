"""定义用户个人资料业务异常及其稳定 HTTP 响应。"""


class UsersError(Exception):
    """用户资料业务错误，携带安全的 HTTP 状态码和提示。"""

    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


class InvalidUserProfileError(UsersError):
    """昵称或头像内容不符合个人资料规则。"""

    def __init__(self, detail: str) -> None:
        super().__init__(422, detail)


class UserProfileNotFoundError(UsersError):
    """当前登录用户资料已不存在。"""

    def __init__(self) -> None:
        super().__init__(404, "用户资料不存在。")


class UsersUnavailableError(UsersError):
    """用户资料依赖的数据库或 OSS 服务暂不可用。"""

    def __init__(self) -> None:
        super().__init__(503, "用户资料服务暂不可用，请稍后重试。")
