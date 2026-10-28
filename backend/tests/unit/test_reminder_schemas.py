from datetime import date

import pytest
from pydantic import ValidationError

from app.modules.reminders.schemas import ReminderCreateRequest


def _valid_payload() -> dict[str, object]:
    """返回最小有效的单次提醒请求。"""

    return {
        "title": "  提交周报  ",
        "content": "  整理本周进展。  ",
        "repeat_type": "once",
        "timezone": "Asia/Shanghai",
        "date": date(2026, 10, 30),
        "local_time": "09:30",
    }


def test_schedule_request_trims_user_text_and_parses_minute_time() -> None:
    """请求 DTO 清理文本边缘空白，并将 HH:MM 解析为本地时间。"""

    request = ReminderCreateRequest(**_valid_payload())

    assert request.title == "提交周报"
    assert request.content == "整理本周进展。"
    assert request.local_time.strftime("%H:%M") == "09:30"


@pytest.mark.parametrize("local_time", ["09:30:00", "9:30", "24:00", "+08:00"])
def test_schedule_request_rejects_non_hhmm_time(local_time: str) -> None:
    """不接受秒、非补零格式或超范围时间。"""

    with pytest.raises(ValidationError):
        ReminderCreateRequest(**{**_valid_payload(), "local_time": local_time})


def test_schedule_request_rejects_server_owned_fields() -> None:
    """请求不能覆盖 user_id、状态或计划 instant 等服务端字段。"""

    with pytest.raises(ValidationError):
        ReminderCreateRequest(**{**_valid_payload(), "user_id": 123})
