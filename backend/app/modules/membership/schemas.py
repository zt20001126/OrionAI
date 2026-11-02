"""定义会员模块的请求、响应和数据转换 Schema。"""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, Field, StringConstraints, field_validator

from app.modules.membership.constants import MembershipOrderStatus

SnowflakeIdString = Annotated[
    str,
    StringConstraints(pattern=r"^[1-9][0-9]{0,18}$", max_length=19),
]
MAX_BIGINT_ID = (1 << 63) - 1


class MembershipPlanResponse(BaseModel):
    """可售会员套餐响应，以字符串形式传递 Snowflake ID 和人民币金额。"""

    id: SnowflakeIdString = Field(description="会员套餐 Snowflake ID")
    name: str = Field(description="套餐展示名称")
    price: str = Field(description="人民币售价，保留两位小数")
    duration_days: int = Field(description="套餐固定有效天数")


class CreateMembershipOrderRequest(BaseModel):
    """创建会员订单请求，不接受用户 ID、价格或有效天数等客户端金额参数。"""

    plan_id: SnowflakeIdString = Field(description="用户选择的会员套餐 Snowflake ID")
    request_id: UUID = Field(description="客户端生成的 UUID 幂等请求键")

    @field_validator("plan_id")
    @classmethod
    def validate_plan_id_range(cls, value: str) -> str:
        """确保十进制 ID 能安全映射到数据库 BIGINT。"""

        if int(value) > MAX_BIGINT_ID:
            raise ValueError("会员套餐 ID 超出 BIGINT 范围。")
        return value


class CreateMembershipOrderResponse(BaseModel):
    """会员订单创建响应，包含金额和有效天数的服务端快照。"""

    order_id: SnowflakeIdString = Field(description="新建或幂等复用的会员订单 ID")
    status: MembershipOrderStatus = Field(description="订单支付状态")
    amount: str = Field(description="订单人民币金额快照，保留两位小数")
    duration_days: int = Field(description="订单有效天数快照")
    created_at: datetime = Field(description="订单创建时间，使用 UTC")


class MembershipOrderResponse(BaseModel):
    """本人会员订单响应，供订单详情、回跳查询和订单列表共用。"""

    order_id: SnowflakeIdString = Field(description="会员订单 Snowflake ID")
    plan_id: SnowflakeIdString = Field(description="关联的会员套餐 Snowflake ID")
    plan_name: str = Field(description="关联套餐展示名称")
    amount: str = Field(description="订单人民币金额快照，保留两位小数")
    duration_days: int = Field(description="订单有效天数快照")
    status: MembershipOrderStatus = Field(description="订单支付状态")
    created_at: datetime = Field(description="订单创建时间，使用 UTC")
    paid_at: datetime | None = Field(description="服务端确认付款时间；未付款时为空")


class MembershipOrderPageResponse(BaseModel):
    """本人会员订单分页响应。"""

    items: list[MembershipOrderResponse] = Field(description="当前页的会员订单")
    total: int = Field(description="符合条件的会员订单总数")
    page: int = Field(description="当前页码，从 1 开始")
    page_size: int = Field(description="当前页请求数量")


class MembershipPeriodResponse(BaseModel):
    """会员有效期响应；套餐名称通过订单关联读取，不重复存储。"""

    order_id: SnowflakeIdString = Field(description="产生此会员期限的订单 ID")
    plan_id: SnowflakeIdString = Field(description="对应会员套餐 ID")
    plan_name: str = Field(description="对应会员套餐名称")
    starts_at: datetime = Field(description="期限开始时间，使用 UTC")
    expires_at: datetime = Field(description="期限结束时间，使用 UTC，边界不包含")


class MembershipOverviewResponse(BaseModel):
    """当前用户的会员状态摘要，按服务端 UTC 当前时间动态计算。"""

    active_period: MembershipPeriodResponse | None = Field(description="当前生效期限；无会员时为空")
    upcoming_periods: list[MembershipPeriodResponse] = Field(
        description="按开始时间升序排列的未来期限"
    )
    latest_expired_period: MembershipPeriodResponse | None = Field(
        description="最近一段已过期期限，用于显示最近到期时间"
    )
