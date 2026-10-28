from datetime import UTC, date, datetime, time

import pytest

from app.modules.reminders.errors import ReminderScheduleError
from app.modules.reminders.recurrence import (
    build_repeat_config,
    first_scheduled_at,
    latest_due_occurrence,
    next_occurrence_after,
)


def test_weekly_rule_repeats_on_start_date_weekday() -> None:
    """每周规则沿用开始日星期，并保留用户时区的墙上时间。"""

    config = build_repeat_config(
        "weekly",
        scheduled_date=None,
        start_date=date(2026, 10, 28),
        local_time=time(9, 30),
    )

    assert config["weekday"] == 3
    assert latest_due_occurrence(
        "weekly",
        config,
        "Asia/Shanghai",
        now=datetime(2026, 11, 4, 2, 0, tzinfo=UTC),
        end_date=None,
    ) == datetime(2026, 11, 4, 1, 30, tzinfo=UTC)
    assert next_occurrence_after(
        "weekly",
        config,
        "Asia/Shanghai",
        reference=datetime(2026, 11, 4, 2, 0, tzinfo=UTC),
        end_date=None,
    ) == datetime(2026, 11, 11, 1, 30, tzinfo=UTC)


def test_monthly_rule_skips_months_without_start_day() -> None:
    """每月 31 日规则在二月跳过，下一次仍落在三月 31 日。"""

    config = build_repeat_config(
        "monthly",
        scheduled_date=None,
        start_date=date(2026, 1, 31),
        local_time=time(9, 0),
    )

    assert latest_due_occurrence(
        "monthly",
        config,
        "Asia/Shanghai",
        now=datetime(2026, 2, 28, 3, 0, tzinfo=UTC),
        end_date=None,
    ) == datetime(2026, 1, 31, 1, 0, tzinfo=UTC)
    assert next_occurrence_after(
        "monthly",
        config,
        "Asia/Shanghai",
        reference=datetime(2026, 2, 28, 3, 0, tzinfo=UTC),
        end_date=None,
    ) == datetime(2026, 3, 31, 1, 0, tzinfo=UTC)


def test_daily_downtime_catch_up_returns_only_latest_missed_occurrence() -> None:
    """恢复扫描时返回最新遗漏计划，而非生成全部积压周期。"""

    config = build_repeat_config(
        "daily",
        scheduled_date=None,
        start_date=date(2026, 10, 28),
        local_time=time(9, 30),
    )

    assert latest_due_occurrence(
        "daily",
        config,
        "Asia/Shanghai",
        now=datetime(2026, 10, 30, 2, 0, tzinfo=UTC),
        end_date=None,
    ) == datetime(2026, 10, 30, 1, 30, tzinfo=UTC)


def test_recurring_nonexistent_dst_time_moves_to_first_valid_minute() -> None:
    """周期提醒落入春季跳时区间时顺延到该日第一个有效时刻。"""

    config = build_repeat_config(
        "daily",
        scheduled_date=None,
        start_date=date(2026, 3, 8),
        local_time=time(2, 30),
    )

    assert first_scheduled_at(
        "daily",
        scheduled_date=None,
        start_date=date(2026, 3, 8),
        local_time=time(2, 30),
        timezone_name="America/New_York",
        now=datetime(2026, 3, 7, 12, 0, tzinfo=UTC),
    ) == datetime(2026, 3, 8, 7, 0, tzinfo=UTC)
    assert latest_due_occurrence(
        "daily",
        config,
        "America/New_York",
        now=datetime(2026, 3, 8, 8, 0, tzinfo=UTC),
        end_date=None,
    ) == datetime(2026, 3, 8, 7, 0, tzinfo=UTC)


def test_ambiguous_dst_time_uses_earlier_instant_for_recurrence() -> None:
    """周期提醒落入秋季重复时段时只选 fold=0 对应的较早 instant。"""

    recurring = first_scheduled_at(
        "daily",
        scheduled_date=None,
        start_date=date(2026, 11, 1),
        local_time=time(1, 30),
        timezone_name="America/New_York",
        now=datetime(2026, 10, 31, 12, 0, tzinfo=UTC),
    )
    assert recurring == datetime(2026, 11, 1, 5, 30, tzinfo=UTC)


@pytest.mark.parametrize("local_time", [time(2, 30)])
def test_one_off_nonexistent_dst_time_is_rejected(local_time: time) -> None:
    """单次提醒遇到夏令时不存在的本地时间时返回业务校验错误。"""

    with pytest.raises(ReminderScheduleError):
        first_scheduled_at(
            "once",
            scheduled_date=date(2026, 3, 8),
            start_date=None,
            local_time=local_time,
            timezone_name="America/New_York",
            now=datetime(2026, 3, 7, 12, 0, tzinfo=UTC),
        )


def test_one_off_ambiguous_dst_time_is_rejected() -> None:
    """单次提醒遇到秋季重复的本地时间时要求用户另选时间。"""

    with pytest.raises(ReminderScheduleError):
        first_scheduled_at(
            "once",
            scheduled_date=date(2026, 11, 1),
            start_date=None,
            local_time=time(1, 30),
            timezone_name="America/New_York",
            now=datetime(2026, 10, 31, 12, 0, tzinfo=UTC),
        )
