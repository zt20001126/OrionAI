"""生成正数 BIGINT Snowflake ID，支持同一进程内多线程并发。"""

import threading
import time

from app.core.config import get_settings

SNOWFLAKE_EPOCH_MS = 1_704_067_200_000  # 2024-01-01 UTC
_SEQUENCE_BITS = 12
_WORKER_ID_BITS = 10
_MAX_SEQUENCE = (1 << _SEQUENCE_BITS) - 1
_MAX_WORKER_ID = (1 << _WORKER_ID_BITS) - 1
_TIMESTAMP_SHIFT = _SEQUENCE_BITS + _WORKER_ID_BITS
_WORKER_ID_SHIFT = _SEQUENCE_BITS
_MAX_TIMESTAMP_DELTA = (1 << 41) - 1


class SnowflakeIdGenerator:
    """按时间戳、worker ID 和毫秒内序号生成 63 位正整数。"""

    def __init__(self, worker_id: int) -> None:
        if worker_id < 0 or worker_id >= _MAX_WORKER_ID:
            raise ValueError("worker_id 必须在 0 到 1022 之间，1023 保留给数据迁移。")
        self._worker_id = worker_id
        # 重启时跳过初始化所在毫秒，避免同一 worker 的毫秒内序号从头复用。
        self._last_timestamp_ms = self._current_timestamp_ms()
        self._sequence = _MAX_SEQUENCE
        self._lock = threading.Lock()

    def next_id(self) -> int:
        """生成唯一 ID；时钟回拨或单毫秒序号耗尽时等待时钟前进。"""

        with self._lock:
            timestamp_ms = self._current_timestamp_ms()
            if timestamp_ms < self._last_timestamp_ms:
                timestamp_ms = self._wait_until_after(self._last_timestamp_ms)

            if timestamp_ms == self._last_timestamp_ms:
                self._sequence = (self._sequence + 1) & _MAX_SEQUENCE
                if self._sequence == 0:
                    timestamp_ms = self._wait_until_after(self._last_timestamp_ms)
            else:
                self._sequence = 0

            self._last_timestamp_ms = timestamp_ms
            timestamp_delta = timestamp_ms - SNOWFLAKE_EPOCH_MS
            if timestamp_delta < 0 or timestamp_delta > _MAX_TIMESTAMP_DELTA:
                raise RuntimeError("系统时间超出 Snowflake ID 支持范围。")

            return (
                (timestamp_delta << _TIMESTAMP_SHIFT)
                | (self._worker_id << _WORKER_ID_SHIFT)
                | self._sequence
            )

    @staticmethod
    def _current_timestamp_ms() -> int:
        return time.time_ns() // 1_000_000

    @classmethod
    def _wait_until_after(cls, timestamp_ms: int) -> int:
        """等待系统时钟超过指定毫秒，避免回拨或序号溢出时重复 ID。"""

        current_timestamp_ms = cls._current_timestamp_ms()
        while current_timestamp_ms <= timestamp_ms:
            time.sleep(0.001)
            current_timestamp_ms = cls._current_timestamp_ms()
        return current_timestamp_ms


_id_generator = SnowflakeIdGenerator(get_settings().snowflake_worker_id)


def generate_snowflake_id() -> int:
    """作为 SQLAlchemy client-side default 生成 Snowflake 主键。"""

    return _id_generator.next_id()
