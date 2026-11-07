"""定义会员套餐、订单和当前会员期限 API。"""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query

from app.modules.auth.dependencies import CurrentUser, RegisteredUser, validate_origin
from app.modules.membership.constants import (
    DEFAULT_ORDER_PAGE_SIZE,
    MAX_ORDER_PAGE_SIZE,
    MIN_ORDER_PAGE,
    MembershipOrderStatus,
)
from app.modules.membership.dependencies import (
    MembershipAccessServiceDependency,
    MembershipServiceDependency,
)
from app.modules.membership.schemas import (
    MAX_BIGINT_ID,
    CreateMembershipOrderRequest,
    CreateMembershipOrderResponse,
    MembershipAccessResponse,
    MembershipOrderPageResponse,
    MembershipOrderResponse,
    MembershipOverviewResponse,
    MembershipPlanResponse,
)

router = APIRouter(prefix="/v1/membership", tags=["membership"])
users_router = APIRouter(prefix="/v1/users", tags=["membership"])
OrderId = Annotated[int, Path(gt=0, le=MAX_BIGINT_ID, description="会员订单 Snowflake ID")]
PageNumber = Annotated[int, Query(ge=MIN_ORDER_PAGE, description="页码，从 1 开始")]
PageSize = Annotated[
    int,
    Query(ge=1, le=MAX_ORDER_PAGE_SIZE, description="每页条数，最大 100"),
]


@router.get("/plans", response_model=list[MembershipPlanResponse])
def list_membership_plans(
    service: MembershipServiceDependency,
) -> list[MembershipPlanResponse]:
    """公开读取启用中的会员套餐。"""

    return service.list_plans()


@router.post(
    "/orders",
    response_model=CreateMembershipOrderResponse,
    status_code=201,
    dependencies=[Depends(validate_origin)],
)
def create_membership_order(
    payload: CreateMembershipOrderRequest,
    user: RegisteredUser,
    service: MembershipServiceDependency,
) -> CreateMembershipOrderResponse:
    """为当前注册用户创建会员订单并快照套餐价格和期限。"""

    return service.create_order(
        user_id=user.id,
        plan_id=int(payload.plan_id),
        request_id=payload.request_id,
    )


@router.get("/orders/{order_id}", response_model=MembershipOrderResponse)
def get_membership_order(
    order_id: OrderId,
    user: RegisteredUser,
    service: MembershipServiceDependency,
) -> MembershipOrderResponse:
    """查询当前注册用户自己的会员订单。"""

    return service.get_order(user_id=user.id, order_id=order_id)


@users_router.get("/me/membership", response_model=MembershipOverviewResponse)
def get_my_membership(
    user: RegisteredUser,
    service: MembershipServiceDependency,
) -> MembershipOverviewResponse:
    """读取当前、未来和最近过期的会员期限。"""

    return service.get_overview(user_id=user.id)


@users_router.get("/me/membership/access", response_model=MembershipAccessResponse)
def get_my_membership_access(
    user: CurrentUser,
    service: MembershipAccessServiceDependency,
) -> MembershipAccessResponse:
    """从 Redis 准入缓存读取当前用户是否可使用技能。"""

    return MembershipAccessResponse(
        is_member=service.is_member(user.id, is_guest=user.is_guest),
    )


@users_router.get("/me/membership/orders", response_model=MembershipOrderPageResponse)
def list_my_membership_orders(
    user: RegisteredUser,
    service: MembershipServiceDependency,
    page: PageNumber = 1,
    page_size: PageSize = DEFAULT_ORDER_PAGE_SIZE,
    status: Annotated[MembershipOrderStatus | None, Query(description="按订单状态筛选")] = None,
) -> MembershipOrderPageResponse:
    """分页读取当前注册用户的会员订单历史。"""

    return service.list_orders(user_id=user.id, page=page, page_size=page_size, status=status)
