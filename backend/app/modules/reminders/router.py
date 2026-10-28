"""定义登录保护的提醒 REST API，并将业务操作委托给 ReminderService。"""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query

from app.modules.auth.dependencies import validate_origin
from app.modules.reminders.constants import MAX_SNOWFLAKE_ID, PAGE_SIZE_DEFAULT, PAGE_SIZE_MAX
from app.modules.reminders.dependencies import CurrentUser, ReminderServiceDependency
from app.modules.reminders.schemas import (
    ReminderCreateRequest,
    ReminderExecutionListQuery,
    ReminderExecutionListResponse,
    ReminderListQuery,
    ReminderListResponse,
    ReminderResponse,
    ReminderStatus,
    ReminderUpdateRequest,
)

router = APIRouter(prefix="/v1/reminders", tags=["reminders"])
ReminderIdPath = Annotated[int, Path(ge=1, le=MAX_SNOWFLAKE_ID)]
ReminderStatusQuery = Annotated[ReminderStatus | None, Query()]
ReminderLimitQuery = Annotated[int, Query(ge=1, le=PAGE_SIZE_MAX)]
ReminderOffsetQuery = Annotated[int, Query(ge=0)]


@router.post(
    "",
    response_model=ReminderResponse,
    status_code=201,
    dependencies=[Depends(validate_origin)],
)
def create_reminder(
    payload: ReminderCreateRequest,
    user: CurrentUser,
    service: ReminderServiceDependency,
) -> ReminderResponse:
    """为当前登录用户创建一个单次或周期提醒。"""

    return service.create(user, payload)


@router.get("", response_model=ReminderListResponse)
def list_reminders(
    user: CurrentUser,
    service: ReminderServiceDependency,
    status: ReminderStatusQuery = None,
    limit: ReminderLimitQuery = PAGE_SIZE_DEFAULT,
    offset: ReminderOffsetQuery = 0,
) -> ReminderListResponse:
    """分页读取当前用户自己的提醒。"""

    return service.list(
        user,
        ReminderListQuery(status=status, limit=limit, offset=offset),
    )


@router.get("/{reminder_id}", response_model=ReminderResponse)
def get_reminder(
    reminder_id: ReminderIdPath,
    user: CurrentUser,
    service: ReminderServiceDependency,
) -> ReminderResponse:
    """读取当前用户的一条提醒；跨用户 ID 与不存在 ID 使用同一 404。"""

    return service.get(user, reminder_id)


@router.put(
    "/{reminder_id}",
    response_model=ReminderResponse,
    dependencies=[Depends(validate_origin)],
)
def update_reminder(
    reminder_id: ReminderIdPath,
    payload: ReminderUpdateRequest,
    user: CurrentUser,
    service: ReminderServiceDependency,
) -> ReminderResponse:
    """用完整规则更新提醒，并以 expected_version 拒绝过期表单。"""

    return service.update(user, reminder_id, payload)


@router.post(
    "/{reminder_id}/pause",
    response_model=ReminderResponse,
    dependencies=[Depends(validate_origin)],
)
def pause_reminder(
    reminder_id: ReminderIdPath,
    user: CurrentUser,
    service: ReminderServiceDependency,
) -> ReminderResponse:
    """暂停周期提醒，已开始的 SMTP 调用无法撤回。"""

    return service.pause(user, reminder_id)


@router.post(
    "/{reminder_id}/resume",
    response_model=ReminderResponse,
    dependencies=[Depends(validate_origin)],
)
def resume_reminder(
    reminder_id: ReminderIdPath,
    user: CurrentUser,
    service: ReminderServiceDependency,
) -> ReminderResponse:
    """恢复暂停的周期提醒并计算下一次未来计划。"""

    return service.resume(user, reminder_id)


@router.post(
    "/{reminder_id}/cancel",
    response_model=ReminderResponse,
    dependencies=[Depends(validate_origin)],
)
def cancel_reminder(
    reminder_id: ReminderIdPath,
    user: CurrentUser,
    service: ReminderServiceDependency,
) -> ReminderResponse:
    """软取消提醒，保留所有已经创建的执行历史。"""

    return service.cancel(user, reminder_id)


@router.get(
    "/{reminder_id}/executions",
    response_model=ReminderExecutionListResponse,
)
def list_reminder_executions(
    reminder_id: ReminderIdPath,
    user: CurrentUser,
    service: ReminderServiceDependency,
    limit: ReminderLimitQuery = PAGE_SIZE_DEFAULT,
    offset: ReminderOffsetQuery = 0,
) -> ReminderExecutionListResponse:
    """读取本人提醒的执行历史，并只返回脱敏后的收件邮箱。"""

    return service.list_executions(
        user,
        reminder_id,
        ReminderExecutionListQuery(limit=limit, offset=offset),
    )
