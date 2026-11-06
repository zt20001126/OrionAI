"""将数字人整理的提醒参数交给现有提醒服务创建。"""

from datetime import date, time

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from app.infrastructure.database.session import SessionLocal
from app.infrastructure.redis.client import create_redis_client
from app.modules.auth.models import User
from app.modules.membership.access_cache import MembershipAccessCache
from app.modules.membership.access_service import MembershipAccessService
from app.modules.membership.errors import MembershipError
from app.modules.reminders.errors import ReminderError
from app.modules.reminders.schemas import ReminderCreateRequest, RepeatType
from app.modules.reminders.service import ReminderService


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
