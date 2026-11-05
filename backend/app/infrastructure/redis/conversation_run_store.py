"""通过 Redis 保存对话生成任务及可重放的 SSE 事件。"""

import json
from typing import Any

from redis import Redis
from redis.exceptions import RedisError

RUN_TTL_SECONDS = 60 * 60
RUN_ACTIVE_TTL_SECONDS = 60
EVENT_BATCH_SIZE = 100


class ConversationRunStore:
    """维护生成任务状态和事件流，供切换页面后的监听恢复使用。"""

    def __init__(self, redis_client: Redis, key_prefix: str = "orionai:conversation-run") -> None:
        self._redis = redis_client
        self._prefix = key_prefix

    def create(self, run_id: str, user_id: int, conversation_id: int) -> None:
        """创建运行记录；输入为任务、用户和会话标识，供对话服务调用。"""
        try:
            created = self._redis.eval(
                "if redis.call('EXISTS', KEYS[1]) == 1 then return 0 end "
                "redis.call('HSET', KEYS[2], 'user_id', ARGV[1], 'conversation_id', ARGV[2], "
                "'status', 'running') "
                "redis.call('EXPIRE', KEYS[2], ARGV[4]) "
                "redis.call('SET', KEYS[1], ARGV[3], 'EX', ARGV[4]) "
                "redis.call('EXPIRE', KEYS[3], ARGV[4]) return 1",
                3,
                self._active_key(user_id, conversation_id),
                self._meta_key(run_id),
                self._events_key(run_id),
                user_id,
                conversation_id,
                run_id,
                RUN_TTL_SECONDS,
            )
            if not created:
                raise RuntimeError("当前会话已有正在生成的回复")
        except RedisError as error:
            raise RuntimeError("无法创建对话生成任务") from error

    def append(self, run_id: str, event: dict[str, Any]) -> None:
        """追加可回放事件，并刷新任务 TTL。"""
        self._redis.xadd(
            self._events_key(run_id), {"payload": json.dumps(event, ensure_ascii=False)}
        )
        self._redis.expire(self._events_key(run_id), RUN_TTL_SECONDS)
        self._redis.expire(self._meta_key(run_id), RUN_TTL_SECONDS)

    def set_status(self, run_id: str, status: str) -> None:
        """更新任务终态或中断请求状态。"""
        self._redis.hset(self._meta_key(run_id), "status", status)
        self._redis.expire(self._meta_key(run_id), RUN_TTL_SECONDS)
        meta = self.get(run_id)
        if status in {"completed", "interrupted", "failed"}:
            self._redis.eval(
                "if redis.call('GET', KEYS[1]) == ARGV[1] then "
                "return redis.call('DEL', KEYS[1]) end return 0",
                1,
                self._active_key(int(meta["user_id"]), int(meta["conversation_id"])),
                run_id,
            )

    def request_interrupt(self, run_id: str) -> bool:
        """请求停止任务；仅允许将运行中任务切换到中断请求态。"""
        return bool(
            self._redis.eval(
                "if redis.call('HGET', KEYS[1], 'status') == 'running' then "
                "redis.call('HSET', KEYS[1], 'status', 'interrupt_requested'); "
                "return 1 end return 0",
                1,
                self._meta_key(run_id),
            )
        )

    def get(self, run_id: str) -> dict[str, str]:
        """读取任务归属和状态；缺失任务返回空映射。"""
        return self._redis.hgetall(self._meta_key(run_id))

    def heartbeat(self, run_id: str) -> None:
        """续期活动任务租约；后端进程异常退出后活动索引可在一分钟内失效。"""
        meta = self.get(run_id)
        if not meta:
            return
        self._redis.expire(self._meta_key(run_id), RUN_ACTIVE_TTL_SECONDS)
        self._redis.eval(
            "if redis.call('GET', KEYS[1]) == ARGV[1] then "
            "return redis.call('EXPIRE', KEYS[1], ARGV[2]) end return 0",
            1,
            self._active_key(int(meta["user_id"]), int(meta["conversation_id"])),
            run_id,
            RUN_ACTIVE_TTL_SECONDS,
        )

    def active(self, user_id: int, conversation_id: int) -> str | None:
        """返回当前用户会话中尚在运行的任务。"""
        run_id = self._redis.get(self._active_key(user_id, conversation_id))
        if not run_id:
            return None
        return (
            run_id if self.get(run_id).get("status") in {"running", "interrupt_requested"} else None
        )

    def events(self, run_id: str, cursor: str = "0-0") -> list[tuple[str, dict[str, Any]]]:
        """读取游标之后的事件，监听断线后可从上次位置恢复。"""
        rows = self._redis.xrange(
            self._events_key(run_id), min=f"({cursor}", count=EVENT_BATCH_SIZE
        )
        return [(event_id, json.loads(fields["payload"])) for event_id, fields in rows]

    def _meta_key(self, run_id: str) -> str:
        return f"{self._prefix}:{run_id}:meta"

    def _events_key(self, run_id: str) -> str:
        return f"{self._prefix}:{run_id}:events"

    def _active_key(self, user_id: int, conversation_id: int) -> str:
        return f"{self._prefix}:active:{user_id}:{conversation_id}"
