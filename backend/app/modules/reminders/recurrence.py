"""实现提醒规则的本地日历计算、UTC 转换及夏令时边界处理。"""

from __future__ import annotations

from calendar import monthrange
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.modules.reminders.constants import (
    MAX_LOCAL_TIME_SHIFT_MINUTES,
    MAX_MONTHLY_SEARCH_MONTHS,
    REPEAT_DAILY,
    REPEAT_MONTHLY,
    REPEAT_ONCE,
    REPEAT_WEEKLY,
)
from app.modules.reminders.errors import ReminderScheduleError


def build_repeat_config(
    repeat_type: str,
    *,
    scheduled_date: date | None,
    start_date: date | None,
    local_time: time,
) -> dict[str, str | int]:
    """从已校验请求构造稳定、具类型的周期 JSON 规则。"""

    if repeat_type == REPEAT_ONCE:
        return {}
    if start_date is None:
        raise ReminderScheduleError
    config: dict[str, str | int] = {
        "start_date": start_date.isoformat(),
        "local_time": local_time.strftime("%H:%M"),
    }
    if repeat_type == REPEAT_WEEKLY:
        config["weekday"] = start_date.isoweekday()
    elif repeat_type == REPEAT_MONTHLY:
        config["day_of_month"] = start_date.day
    elif repeat_type != REPEAT_DAILY:
        raise ReminderScheduleError
    return config


def first_scheduled_at(
    repeat_type: str,
    *,
    scheduled_date: date | None,
    start_date: date | None,
    local_time: time,
    timezone_name: str,
    now: datetime,
) -> datetime:
    """将创建规则的首次本地时间换算为未来 UTC instant，并拒绝过去计划。"""

    zone = _get_zone(timezone_name)
    local_date = scheduled_date if repeat_type == REPEAT_ONCE else start_date
    if local_date is None:
        raise ReminderScheduleError
    candidate = _resolve_local_datetime(
        local_date,
        local_time,
        zone,
        reject_ambiguous=repeat_type == REPEAT_ONCE,
        shift_nonexistent=repeat_type != REPEAT_ONCE,
    ).astimezone(UTC)
    if candidate <= _as_utc(now):
        raise ReminderScheduleError("首次提醒时间必须晚于当前时间。")
    return candidate


def latest_due_occurrence(
    repeat_type: str,
    repeat_config: dict[str, Any],
    timezone_name: str,
    *,
    now: datetime,
    end_date: date | None,
) -> datetime | None:
    """计算截至当前时刻最近一次实际存在的周期计划，折叠停机积压。"""

    if repeat_type == REPEAT_ONCE:
        return None
    zone = _get_zone(timezone_name)
    local_now = _as_utc(now).astimezone(zone)
    start_date = _config_date(repeat_config, "start_date")
    local_time = _config_time(repeat_config)
    upper_date = min(local_now.date(), end_date) if end_date else local_now.date()

    if repeat_type == REPEAT_DAILY:
        candidate_date = upper_date
        while candidate_date >= start_date:
            candidate = _resolve_local_datetime(
                candidate_date, local_time, zone, shift_nonexistent=True
            ).astimezone(UTC)
            if candidate <= _as_utc(now):
                return candidate
            candidate_date -= timedelta(days=1)
        return None

    if repeat_type == REPEAT_WEEKLY:
        weekday = _config_int(repeat_config, "weekday")
        days_back = (upper_date.isoweekday() - weekday) % 7
        candidate_date = upper_date - timedelta(days=days_back)
        if candidate_date < start_date:
            return None
        candidate = _resolve_local_datetime(
            candidate_date, local_time, zone, shift_nonexistent=True
        ).astimezone(UTC)
        if candidate > _as_utc(now):
            candidate_date -= timedelta(days=7)
            if candidate_date < start_date:
                return None
            candidate = _resolve_local_datetime(
                candidate_date, local_time, zone, shift_nonexistent=True
            ).astimezone(UTC)
        return candidate if candidate <= _as_utc(now) else None

    if repeat_type == REPEAT_MONTHLY:
        day_of_month = _config_int(repeat_config, "day_of_month")
        year, month = upper_date.year, upper_date.month
        for _ in range(MAX_MONTHLY_SEARCH_MONTHS):
            days_in_month = monthrange(year, month)[1]
            if day_of_month <= days_in_month:
                candidate_date = date(year, month, day_of_month)
                if candidate_date < start_date:
                    return None
                candidate = _resolve_local_datetime(
                    candidate_date, local_time, zone, shift_nonexistent=True
                ).astimezone(UTC)
                if candidate <= _as_utc(now):
                    return candidate
            year, month = _previous_month(year, month)
            if (year, month) < (start_date.year, start_date.month):
                return None
        raise ReminderScheduleError("月度提醒规则超出可计算范围。")

    raise ReminderScheduleError


def next_occurrence_after(
    repeat_type: str,
    repeat_config: dict[str, Any],
    timezone_name: str,
    *,
    reference: datetime,
    end_date: date | None,
) -> datetime | None:
    """返回严格晚于参考 instant 的第一个有效周期计划。"""

    if repeat_type == REPEAT_ONCE:
        return None
    zone = _get_zone(timezone_name)
    reference_utc = _as_utc(reference)
    local_reference = reference_utc.astimezone(zone)
    start_date = _config_date(repeat_config, "start_date")
    local_time = _config_time(repeat_config)

    if repeat_type == REPEAT_DAILY:
        candidate_date = max(start_date, local_reference.date())
        for _ in range(MAX_MONTHLY_SEARCH_MONTHS * 31):
            candidate = _resolve_local_datetime(
                candidate_date, local_time, zone, shift_nonexistent=True
            ).astimezone(UTC)
            if candidate > reference_utc:
                return candidate if end_date is None or candidate_date <= end_date else None
            candidate_date += timedelta(days=1)
        raise ReminderScheduleError("日度提醒规则超出可计算范围。")

    if repeat_type == REPEAT_WEEKLY:
        weekday = _config_int(repeat_config, "weekday")
        candidate_date = local_reference.date()
        days_until = (weekday - candidate_date.isoweekday()) % 7
        candidate_date += timedelta(days=days_until)
        candidate_date = max(candidate_date, start_date)
        if candidate_date.isoweekday() != weekday:
            candidate_date += timedelta(days=(weekday - candidate_date.isoweekday()) % 7)
        for _ in range(MAX_MONTHLY_SEARCH_MONTHS * 5):
            candidate = _resolve_local_datetime(
                candidate_date, local_time, zone, shift_nonexistent=True
            ).astimezone(UTC)
            if candidate > reference_utc:
                return candidate if end_date is None or candidate_date <= end_date else None
            candidate_date += timedelta(days=7)
        raise ReminderScheduleError("周度提醒规则超出可计算范围。")

    if repeat_type == REPEAT_MONTHLY:
        day_of_month = _config_int(repeat_config, "day_of_month")
        year, month = local_reference.year, local_reference.month
        for _ in range(MAX_MONTHLY_SEARCH_MONTHS):
            days_in_month = monthrange(year, month)[1]
            if day_of_month <= days_in_month:
                candidate_date = date(year, month, day_of_month)
                if candidate_date >= start_date:
                    candidate = _resolve_local_datetime(
                        candidate_date, local_time, zone, shift_nonexistent=True
                    ).astimezone(UTC)
                    if candidate > reference_utc:
                        return candidate if end_date is None or candidate_date <= end_date else None
            year, month = _next_month(year, month)
            if end_date and (year, month) > (end_date.year, end_date.month):
                return None
        raise ReminderScheduleError("月度提醒规则超出可计算范围。")

    raise ReminderScheduleError


def _resolve_local_datetime(
    local_date: date,
    local_time: time,
    zone: ZoneInfo,
    *,
    reject_ambiguous: bool = False,
    shift_nonexistent: bool = False,
) -> datetime:
    """将本地墙上时间解析为有效时区时间，按方案处理歧义和 DST 跳时。"""

    naive = datetime.combine(local_date, local_time)
    first = naive.replace(tzinfo=zone, fold=0)
    second = naive.replace(tzinfo=zone, fold=1)
    first_valid = _round_trips(first, naive)
    second_valid = _round_trips(second, naive)

    if first_valid or second_valid:
        is_ambiguous = first_valid and second_valid and first.utcoffset() != second.utcoffset()
        if is_ambiguous and reject_ambiguous:
            raise ReminderScheduleError("该本地时间因夏令时出现两次，请选择其他时间。")
        if first_valid:
            return first
        return second

    if not shift_nonexistent:
        raise ReminderScheduleError("该本地时间因夏令时不存在，请选择其他时间。")
    for minute_offset in range(1, MAX_LOCAL_TIME_SHIFT_MINUTES + 1):
        shifted_naive = naive + timedelta(minutes=minute_offset)
        shifted = shifted_naive.replace(tzinfo=zone, fold=0)
        if _round_trips(shifted, shifted_naive):
            return shifted
    raise ReminderScheduleError("无法解析该时区中的本地时间。")


def _round_trips(value: datetime, expected_local: datetime) -> bool:
    """检查指定 fold 转成 UTC 后能否还原成原始本地墙上时间。"""

    return value.astimezone(UTC).astimezone(value.tzinfo).replace(tzinfo=None) == expected_local


def _get_zone(timezone_name: str) -> ZoneInfo:
    """解析已由请求层校验的时区，避免规则计算使用系统本地时区。"""

    try:
        return ZoneInfo(timezone_name)
    except (KeyError, ValueError) as error:
        raise ReminderScheduleError("时区必须是有效的 IANA 时区名称。") from error


def _config_date(config: dict[str, Any], key: str) -> date:
    """从持久化 JSON 规则读取 ISO 日期。"""

    try:
        value = config[key]
        return value if isinstance(value, date) else date.fromisoformat(str(value))
    except (KeyError, TypeError, ValueError) as error:
        raise ReminderScheduleError("提醒周期规则中的日期无效。") from error


def _config_time(config: dict[str, Any]) -> time:
    """从持久化 JSON 规则读取分钟精度本地时间。"""

    try:
        return time.fromisoformat(str(config["local_time"]))
    except (KeyError, TypeError, ValueError) as error:
        raise ReminderScheduleError("提醒周期规则中的时间无效。") from error


def _config_int(config: dict[str, Any], key: str) -> int:
    """读取周期规则中的整数日号或 ISO weekday。"""

    value = config.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ReminderScheduleError("提醒周期规则中的数字无效。")
    return value


def _as_utc(value: datetime) -> datetime:
    """要求业务时间为带时区 datetime 并规范为 UTC。"""

    if value.tzinfo is None:
        raise ReminderScheduleError("服务端时间必须包含时区信息。")
    return value.astimezone(UTC)


def _next_month(year: int, month: int) -> tuple[int, int]:
    """计算下一个公历月份。"""

    return (year + 1, 1) if month == 12 else (year, month + 1)


def _previous_month(year: int, month: int) -> tuple[int, int]:
    """计算上一个公历月份。"""

    return (year - 1, 12) if month == 1 else (year, month - 1)
