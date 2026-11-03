"""数字人业务错误及其安全 HTTP 语义。"""


class DigitalHumanError(Exception):
    """带稳定 HTTP 状态和可公开说明的数字人业务错误。"""

    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


class DigitalHumanValidationError(DigitalHumanError):
    """请求内容不符合数字人业务边界。"""

    def __init__(self, detail: str) -> None:
        super().__init__(422, detail)


class DigitalHumanPayloadTooLargeError(DigitalHumanError):
    """录音请求超过服务端字节上限。"""

    def __init__(self) -> None:
        super().__init__(413, "录音文件超过大小限制。")


class DigitalHumanUnavailableError(DigitalHumanError):
    """数据库或语音 Provider 当前不可用。"""

    def __init__(self, detail: str = "数字人语音服务暂不可用，请稍后重试。") -> None:
        super().__init__(503, detail)
