"""集中维护提醒执行进入终态后的生命周期收束规则。"""

from app.modules.reminders.constants import (
    REMINDER_ACTIVE,
    REMINDER_COMPLETED,
    REPEAT_ONCE,
)
from app.modules.reminders.models import Reminder


def complete_if_no_future(reminder: Reminder) -> None:
    """单次提醒或没有后续计划的周期提醒在最后一次执行终结后完成。"""

    if reminder.status == REMINDER_ACTIVE and (
        reminder.repeat_type == REPEAT_ONCE or reminder.next_run_at is None
    ):
        reminder.status = REMINDER_COMPLETED
        reminder.next_run_at = None
