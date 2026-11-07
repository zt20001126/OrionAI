class AuthError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


class InvalidCodeError(AuthError):
    def __init__(self) -> None:
        super().__init__(400, "验证码无效或已过期。")


class InvalidCredentialsError(AuthError):
    def __init__(self) -> None:
        super().__init__(401, "邮箱或密码错误。")


class PasswordPolicyError(AuthError):
    def __init__(self, detail: str) -> None:
        super().__init__(422, detail)


class AccountExistsError(AuthError):
    def __init__(self) -> None:
        super().__init__(409, "该邮箱已注册。")


class RateLimitError(AuthError):
    def __init__(self) -> None:
        super().__init__(429, "请求过于频繁，请稍后重试。")


class AuthUnavailableError(AuthError):
    def __init__(self) -> None:
        super().__init__(503, "认证服务暂不可用，请稍后重试。")


class OAuthError(AuthError):
    def __init__(self, detail: str = "第三方登录失败，请重试。") -> None:
        super().__init__(400, detail)


class OAuthEmailConflictError(AuthError):
    def __init__(self) -> None:
        super().__init__(409, "该邮箱已注册，请先使用邮箱登录，再绑定 Gitee 账号。")


class OAuthAccountConflictError(AuthError):
    def __init__(self) -> None:
        super().__init__(409, "该 Gitee 账号已被其他用户绑定，或当前账号已经绑定 Gitee。")
