"""定义支付方式、Checkout Session 和 Webhook 的请求及响应 Schema。"""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints, field_validator

from app.modules.membership.schemas import MAX_BIGINT_ID, SnowflakeIdString


class CreateCheckoutSessionRequest(BaseModel):
    """创建或重新获取 Checkout Session 请求。"""

    order_id: SnowflakeIdString = Field(description="待支付的会员订单 Snowflake ID")
    payment_method: Annotated[
        str,
        StringConstraints(min_length=1, max_length=32, pattern=r"^[a-z0-9_-]+$"),
    ] = Field(description="动态支付方式列表返回的渠道编码")

    @field_validator("order_id")
    @classmethod
    def validate_order_id_range(cls, value: str) -> str:
        """确保订单 ID 能安全映射到数据库 BIGINT。"""

        if int(value) > MAX_BIGINT_ID:
            raise ValueError("会员订单 ID 超出 BIGINT 范围。")
        return value


class StripeCheckoutSessionRequest(BaseModel):
    """Stripe Checkout Session 兼容接口请求。"""

    order_id: SnowflakeIdString = Field(description="待支付的会员订单 Snowflake ID")

    @field_validator("order_id")
    @classmethod
    def validate_order_id_range(cls, value: str) -> str:
        """确保订单 ID 能安全映射到数据库 BIGINT。"""

        if int(value) > MAX_BIGINT_ID:
            raise ValueError("会员订单 ID 超出 BIGINT 范围。")
        return value


class PaymentMethodResponse(BaseModel):
    """当前运行环境实际可用的支付方式。"""

    code: str = Field(description="支付渠道编码")
    name: str = Field(description="支付渠道展示名称")
    description: str | None = Field(description="支付渠道说明；无说明时为空")


class CheckoutSessionResponse(BaseModel):
    """Checkout Session 创建或恢复响应。"""

    order_id: SnowflakeIdString = Field(description="关联的会员订单 Snowflake ID")
    checkout_url: str = Field(description="Stripe 返回的 HTTPS 托管支付页面地址")
    expires_at: datetime = Field(description="Stripe Checkout Session 到期时间，使用 UTC")


class StripeWebhookAcknowledgement(BaseModel):
    """Stripe Webhook 接收确认响应。"""

    received: bool = Field(description="已接收并处理或安全忽略该事件")
