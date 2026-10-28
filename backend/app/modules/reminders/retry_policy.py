"""集中计算有限重试间隔及其随机抖动。"""

from __future__ import annotations

import random
from datetime import timedelta

from app.modules.reminders.constants import RETRY_DELAYS, RETRY_JITTER_RATIO


def retry_delay(retry_count: int) -> timedelta:
    """返回对应重试次数的退避时长，并加入小幅随机抖动。"""

    if retry_count < 1 or retry_count > len(RETRY_DELAYS):
        raise ValueError("重试次数超出策略范围。")

    base_delay = RETRY_DELAYS[retry_count - 1]
    jitter_ratio = random.uniform(-RETRY_JITTER_RATIO, RETRY_JITTER_RATIO)
    return base_delay * (1 + jitter_ratio)
