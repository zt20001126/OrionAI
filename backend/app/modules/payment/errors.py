"""定义支付模块可安全返回给 API 调用方的业务异常。"""


class PaymentError(Exception):
    """支付业务错误，携带稳定 HTTP 状态码和中文说明。"""

    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


class PaymentConflictError(PaymentError):
    """会员订单状态不允许创建或恢复 Checkout Session。"""

    def __init__(self, detail: str) -> None:
        super().__init__(409, detail)


class PaymentMethodUnavailableError(PaymentError):
    """客户端选择的支付渠道当前不可用。"""

    def __init__(self) -> None:
        super().__init__(404, "所选支付方式当前不可用。")


class PaymentSignatureError(PaymentError):
    """Stripe Webhook 签名验证失败或签名头缺失。"""

    def __init__(self) -> None:
        super().__init__(400, "Stripe Webhook 签名无效。")


class PaymentUnavailableError(PaymentError):
    """Stripe 配置、第三方 API 或支付持久化当前不可用。"""

    def __init__(self) -> None:
        super().__init__(503, "支付服务暂时不可用，请稍后重试。")
