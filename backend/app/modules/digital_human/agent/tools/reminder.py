"""将数字人整理的提醒参数交给现有提醒服务创建。"""

import json
from datetime import date, time

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.infrastructure.database.session import SessionLocal
from app.infrastructure.redis.client import create_redis_client
from app.modules.auth.models import User
from app.modules.membership.access_cache import MembershipAccessCache
from app.modules.membership.access_service import MembershipAccessService
from app.modules.membership.errors import MembershipError
from app.modules.reminders.constants import PAGE_SIZE_DEFAULT, PAGE_SIZE_MAX
from app.modules.reminders.errors import ReminderError
from app.modules.reminders.schemas import (
    ReminderCreateRequest,
    ReminderListQuery,
    ReminderStatus,
    RepeatType,
    validate_snowflake_range,
)
from app.modules.reminders.service import ReminderService


class ReminderDetailInput(BaseModel):
    """提醒详情查询参数；提醒 ID 必须由当前用户的列表结果获得。"""

    model_config = ConfigDict(extra="forbid")

    reminder_id: str = Field(description="提醒 ID，使用十进制字符串")

    @field_validator("reminder_id")
    @classmethod
    def validate_reminder_id(cls, value: str) -> str:
        """校验详情查询 ID 的格式与数据库范围。"""
        validate_snowflake_range(value)
        return value


class ReminderListToolInput(BaseModel):
    """当前用户提醒列表的筛选和分页参数。"""

    model_config = ConfigDict(extra="forbid")

    status: ReminderStatus | None = Field(default=None, description="可选状态筛选")
    limit: int = Field(default=PAGE_SIZE_DEFAULT, ge=1, le=PAGE_SIZE_MAX, description="每页条数")
    offset: int = Field(default=0, ge=0, description="从第几条开始读取")


@tool("create_reminder", args_schema=ReminderCreateRequest)
def create_reminder(
    config: RunnableConfig,
    title: str,
    content: str,
    repeat_type: RepeatType,
    timezone: str,
    local_time: time,
    date: date | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> str:
    """为当前用户创建提醒；输入完整计划，输出创建结果；调用方：数字人。"""
    payload = ReminderCreateRequest(
        title=title,
        content=content,
        repeat_type=repeat_type,
        timezone=timezone,
        local_time=local_time,
        date=date,
        start_date=start_date,
        end_date=end_date,
    )
    user_id = int(config["configurable"]["user_id"])
    client = create_redis_client()
    try:
        with SessionLocal() as session:
            user = session.get(User, user_id)
            if user is None:
                return "提醒创建失败：当前用户不存在。"
            try:
                MembershipAccessService(session, MembershipAccessCache(client)).require_member(
                    user.id, is_guest=user.is_guest
                )
                created = ReminderService(session).create(user, payload)
            except (MembershipError, ReminderError) as error:
                return f"提醒创建失败：{error.detail}"
            return (
                f"提醒已创建。ID：{created.id}；标题：{created.title}；"
                f"类型：{created.repeat_type}；时区：{created.timezone}；"
                f"下次执行时间（UTC）：{created.next_run_at.isoformat()}。"
            )
    finally:
        client.close()


@tool("list_reminders", args_schema=ReminderListToolInput)
def list_reminders(
    config: RunnableConfig,
    status: ReminderStatus | None = None,
    limit: int = PAGE_SIZE_DEFAULT,
    offset: int = 0,
) -> str:
    """分页查询当前用户提醒；输入状态和分页，输出提醒列表；调用方：数字人。"""
    query = ReminderListQuery(status=status, limit=limit, offset=offset)
    user_id = int(config["configurable"]["user_id"])
    with SessionLocal() as session:
        user = session.get(User, user_id)
        if user is None:
            return "提醒查询失败：当前用户不存在。"
        try:
            result = ReminderService(session).list(user, query)
        except ReminderError as error:
            return f"提醒查询失败：{error.detail}"
        payload = result.model_dump(mode="json")
        payload["has_more"] = result.offset + len(result.items) < result.total
        return json.dumps(payload, ensure_ascii=False)


@tool("get_reminder", args_schema=ReminderDetailInput)
def get_reminder(config: RunnableConfig, reminder_id: str) -> str:
    """查询当前用户的一条提醒详情；输入提醒 ID，输出详情；调用方：数字人。"""
    validated_id = validate_snowflake_range(reminder_id)
    user_id = int(config["configurable"]["user_id"])
    with SessionLocal() as session:
        user = session.get(User, user_id)
        if user is None:
            return "提醒查询失败：当前用户不存在。"
        try:
            result = ReminderService(session).get(user, validated_id)
        except ReminderError as error:
            return f"提醒查询失败：{error.detail}"
        return result.model_dump_json()
