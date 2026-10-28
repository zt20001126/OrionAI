"""定义提醒 API 的严格请求 DTO、响应 DTO 和字段业务约束。"""

from __future__ import annotations

import re
from datetime import date as Date
from datetime import datetime
from datetime import time as Time
from typing import Annotated, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.modules.reminders.constants import (
    CONTENT_MAX_LENGTH,
    MAX_SNOWFLAKE_ID,
    PAGE_SIZE_DEFAULT,
    PAGE_SIZE_MAX,
    TIMEZONE_MAX_LENGTH,
    TITLE_MAX_LENGTH,
)

RepeatType = Literal["once", "daily", "weekly", "monthly"]
ReminderStatus = Literal["active", "paused", "cancelled", "completed"]
ExecutionStatus = Literal["pending", "sending", "retry_wait", "accepted", "failed", "cancelled"]
SnowflakeId = Annotated[str, Field(pattern=r"^[1-9][0-9]{0,18}$")]
LOCAL_TIME_PATTERN = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")


class StrictRequest(BaseModel):
    """提醒请求的共同基类，拒绝未声明字段以避免客户端覆盖服务端状态。"""

    model_config = ConfigDict(extra="forbid")


class ReminderScheduleRequest(StrictRequest):
    """创建或替换提醒规则的字段，所有日期和时间均为用户时区的本地值。"""

    title: str = Field(description="提醒标题，去除首尾空格后为 1 到 120 个字符")
    content: str = Field(description="提醒正文，去除首尾空格后为 1 到 5000 个字符")
    repeat_type: RepeatType = Field(description="单次、每天、每周或每月重复")
    timezone: str = Field(max_length=TIMEZONE_MAX_LENGTH, description="IANA 时区名称")
    date: Date | None = Field(default=None, description="单次提醒的本地日期")
    start_date: Date | None = Field(default=None, description="周期提醒的本地开始日期")
    local_time: Time = Field(description="用户时区中的本地提醒时间")
    end_date: Date | None = Field(default=None, description="周期提醒包含的最后一个本地日期")

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        """去掉标题两侧空格，并确保标题在业务长度范围内。"""

        normalized = value.strip()
        if not normalized or len(normalized) > TITLE_MAX_LENGTH:
            raise ValueError("标题不能为空且不能超过 120 个字符")
        return normalized

    @field_validator("content")
    @classmethod
    def normalize_content(cls, value: str) -> str:
        """去掉正文两侧空格，并确保正文在业务长度范围内。"""

        normalized = value.strip()
        if not normalized or len(normalized) > CONTENT_MAX_LENGTH:
            raise ValueError("提醒内容不能为空且不能超过 5000 个字符")
        return normalized

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        """只接受系统可解析的 IANA 时区，不接受固定 UTC 偏移字符串。"""

        normalized = value.strip()
        if not normalized:
            raise ValueError("时区不能为空")
        try:
            ZoneInfo(normalized)
        except ZoneInfoNotFoundError as error:
            raise ValueError("时区必须是有效的 IANA 时区名称") from error
        return normalized

    @field_validator("local_time", mode="before")
    @classmethod
    def validate_local_time(cls, value: object) -> object:
        """限制为不带时区的分钟精度本地墙上时间。"""

        if isinstance(value, str) and not LOCAL_TIME_PATTERN.fullmatch(value):
            raise ValueError("提醒时间必须是 HH:MM 格式")
        if not isinstance(value, (str, Time)):
            raise ValueError("提醒时间必须是 HH:MM 格式")
        if isinstance(value, str):
            value = Time.fromisoformat(value)
        if value.tzinfo is not None or value.second != 0 or value.microsecond != 0:
            raise ValueError("提醒时间必须是 HH:MM 格式")
        return value

    @model_validator(mode="after")
    def validate_schedule_fields(self) -> ReminderScheduleRequest:
        """校验单次与周期字段互斥，并确保结束日落在开始日之后。"""

        if self.repeat_type == "once":
            if self.date is None or self.start_date is not None or self.end_date is not None:
                raise ValueError("单次提醒必须填写 date，且不能填写周期日期")
            return self

        if self.start_date is None or self.date is not None:
            raise ValueError("周期提醒必须填写 start_date，且不能填写 date")
        if self.end_date is not None and self.end_date < self.start_date:
            raise ValueError("结束日期不能早于开始日期")
        return self


class ReminderCreateRequest(ReminderScheduleRequest):
    """创建提醒请求，不允许客户端指定用户、状态、计划 instant 或收件邮箱。"""


class ReminderUpdateRequest(ReminderScheduleRequest):
    """完整替换提醒规则的请求，必须携带读取时的并发版本。"""

    expected_version: int = Field(ge=1, description="客户端读取提醒时获得的版本号")


class ReminderResponse(BaseModel):
    """提醒资源响应，Snowflake ID 以十进制字符串传给浏览器。"""

    id: SnowflakeId = Field(description="提醒 Snowflake ID")
    title: str = Field(description="提醒标题")
    content: str = Field(description="提醒正文")
    repeat_type: RepeatType = Field(description="重复类型")
    repeat_config: dict[str, str | int] = Field(description="规范化后的周期规则")
    timezone: str = Field(description="IANA 时区名称")
    next_run_at: datetime | None = Field(description="下一次计划时间，ISO 8601 UTC")
    end_date: Date | None = Field(description="包含结束日的本地日历日期")
    status: ReminderStatus = Field(description="提醒生命周期状态")
    version: int = Field(ge=1, description="乐观并发版本号")
    created_at: datetime = Field(description="提醒创建时间")
    updated_at: datetime = Field(description="提醒最后更新时间")


class ReminderListResponse(BaseModel):
    """当前用户提醒分页响应。"""

    items: list[ReminderResponse] = Field(description="当前页提醒")
    total: int = Field(ge=0, description="匹配提醒总数")
    limit: int = Field(description="本页最大记录数")
    offset: int = Field(ge=0, description="本页起始偏移")


class ReminderExecutionResponse(BaseModel):
    """提醒执行历史响应，不向普通用户返回完整收件邮箱。"""

    id: SnowflakeId = Field(description="执行记录 Snowflake ID")
    scheduled_at: datetime = Field(description="本次计划时间，ISO 8601 UTC")
    status: ExecutionStatus = Field(description="执行状态，accepted 仅代表 SMTP 接受")
    retry_count: int = Field(ge=0, description="已发生的失败重试次数")
    next_retry_at: datetime | None = Field(description="下次重试时间")
    recipient_email_masked: str | None = Field(description="脱敏后的收件邮箱")
    error_message: str | None = Field(description="用户可读的安全失败摘要")
    started_at: datetime | None = Field(description="最近一次尝试开始时间")
    finished_at: datetime | None = Field(description="进入终态的时间")
    created_at: datetime = Field(description="执行记录创建时间")


class ReminderExecutionListResponse(BaseModel):
    """提醒执行历史分页响应。"""

    items: list[ReminderExecutionResponse] = Field(description="当前页执行记录")
    total: int = Field(ge=0, description="执行记录总数")
    limit: int = Field(description="本页最大记录数")
    offset: int = Field(ge=0, description="本页起始偏移")


class ReminderListQuery(BaseModel):
    """提醒列表的服务层查询 DTO。"""

    status: ReminderStatus | None = Field(default=None, description="可选提醒状态过滤")
    limit: int = Field(default=PAGE_SIZE_DEFAULT, ge=1, le=PAGE_SIZE_MAX)
    offset: int = Field(default=0, ge=0)


class ReminderExecutionListQuery(BaseModel):
    """提醒执行历史的分页查询 DTO。"""

    limit: int = Field(default=PAGE_SIZE_DEFAULT, ge=1, le=PAGE_SIZE_MAX)
    offset: int = Field(default=0, ge=0)


def validate_snowflake_range(value: str) -> int:
    """将已通过模式校验的 ID 转为整数，并检查数据库有符号 BIGINT 上限。"""

    snowflake_id = int(value)
    if snowflake_id > MAX_SNOWFLAKE_ID:
        raise ValueError("提醒 ID 超出 Snowflake 范围")
    return snowflake_id
