"""协调 Redis 任务状态、后台 Agent 执行和 SSE 监听生命周期。"""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import suppress
from dataclasses import replace
from uuid import uuid4

from redis import Redis

from app.modules.conversations.errors import (
    ConversationConflictError,
    ConversationNotFoundError,
    ConversationUnavailableError,
)
from app.modules.conversations.models import Conversation
from app.modules.conversations.run_store import ConversationRunStore
from app.modules.conversations.service import ConversationService, PreparedConversationTurn
from app.shared.streaming import EventType, StreamEvent

logger = logging.getLogger(__name__)
LISTEN_POLL_SECONDS = 0.35
RUN_HEARTBEAT_SECONDS = 10


class ConversationRunCoordinator:
    """启动可脱离浏览器连接运行的 Agent 任务，并为多次监听回放事件。"""

    def __init__(self, redis_client: Redis) -> None:
        self._redis = redis_client
        self._store = ConversationRunStore(redis_client)
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._loop: asyncio.AbstractEventLoop | None = None

    def start(self, service: ConversationService, prepared: PreparedConversationTurn) -> str:
        """创建任务并启动独立执行协程；返回本轮生成的 run_id。"""
        conversation_id = prepared.conversation.id
        active = self._store.active(prepared.user_id, conversation_id)
        if active:
            raise ConversationConflictError("当前会话已有正在生成的回复。")
        run_id = uuid4().hex
        self._loop = asyncio.get_running_loop()
        try:
            self._store.create(run_id, prepared.user_id, conversation_id)
        except RuntimeError as error:
            if str(error) == "当前会话已有正在生成的回复":
                raise ConversationConflictError(str(error)) from None
            raise ConversationUnavailableError from error
        snapshot = replace(
            prepared,
            conversation=Conversation(
                id=conversation_id,
                user_id=prepared.user_id,
                skill_code=prepared.conversation.skill_code,
                title=prepared.conversation.title,
            ),
        )
        task = asyncio.create_task(self._execute(run_id, service, snapshot))
        self._tasks[run_id] = task
        task.add_done_callback(lambda _: self._tasks.pop(run_id, None))
        return run_id

    def ensure_available(self, user_id: int, conversation_id: int) -> None:
        """在写入用户消息前拒绝同会话的并行生成。"""
        if self._store.active(user_id, conversation_id):
            raise ConversationConflictError("当前会话已有正在生成的回复。")

    async def listen(
        self, run_id: str, user_id: int, conversation_id: int
    ) -> AsyncIterator[StreamEvent]:
        """回放全部已生成事件并持续读取新事件，连接关闭不影响 Agent。"""
        meta = self._store.get(run_id)
        self._require_owner(meta, user_id, conversation_id)
        cursor = "0-0"
        while True:
            events = await asyncio.to_thread(self._store.events, run_id, cursor)
            for event_id, payload in events:
                cursor = event_id
                yield StreamEvent(event_type=EventType.MESSAGE, data=payload)
            meta = await asyncio.to_thread(self._store.get, run_id)
            if meta.get("status") in {"completed", "interrupted", "failed"}:
                yield StreamEvent(
                    event_type=EventType.MESSAGE,
                    data={"type": "run_status", "status": meta["status"]},
                )
                return
            await asyncio.sleep(LISTEN_POLL_SECONDS)

    def active(self, user_id: int, conversation_id: int) -> str | None:
        """查找该会话当前运行任务，供页面重载或重新进入时恢复监听。"""
        return self._store.active(user_id, conversation_id)

    async def close(self) -> None:
        """应用关闭时取消本进程任务并释放 Redis 连接。"""
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._redis.close()

    def interrupt(self, run_id: str, user_id: int, conversation_id: int) -> None:
        """设置取消状态并向本进程中的生成协程发送取消信号。"""
        meta = self._store.get(run_id)
        self._require_owner(meta, user_id, conversation_id)
        if not self._store.request_interrupt(run_id):
            if meta.get("status") == "interrupted":
                return
            raise ConversationConflictError("本次回复已结束，无法中断。")
        task = self._tasks.get(run_id)
        if task is not None and self._loop is not None:
            self._loop.call_soon_threadsafe(task.cancel)

    async def _execute(
        self,
        run_id: str,
        service: ConversationService,
        prepared: PreparedConversationTurn,
    ) -> None:
        """消费 Agent 流并写入 Redis；任务结束时更新可查询的终态。"""
        worker_task = asyncio.current_task()
        watcher = asyncio.create_task(self._watch_interrupt(run_id, worker_task))
        try:
            await service.execute_background_run(prepared, self._store, run_id)
            if self._store.get(run_id).get("status") == "interrupt_requested":
                self._store.set_status(run_id, "interrupted")
            else:
                self._store.set_status(run_id, "completed")
        except asyncio.CancelledError:
            self._store.set_status(run_id, "interrupted")
        except Exception as error:
            logger.warning(
                "conversation_run_failed run_id=%s error_type=%s", run_id, type(error).__name__
            )
            self._store.set_status(run_id, "failed")
        finally:
            watcher.cancel()
            with suppress(asyncio.CancelledError):
                await watcher

    async def _watch_interrupt(self, run_id: str, worker_task: asyncio.Task[None] | None) -> None:
        """轮询共享 Redis 中断状态，使其它后端实例也能取消本机生成协程。"""
        while worker_task is not None and not worker_task.done():
            meta = await asyncio.to_thread(self._store.get, run_id)
            if meta.get("status") == "interrupt_requested":
                worker_task.cancel()
                return
            await asyncio.to_thread(self._store.heartbeat, run_id)
            await asyncio.sleep(RUN_HEARTBEAT_SECONDS)

    @staticmethod
    def _require_owner(meta: dict[str, str], user_id: int, conversation_id: int) -> None:
        """确保 run_id 只能由所属用户在所属会话中读取或中断。"""
        if not meta:
            raise ConversationNotFoundError()
        if meta.get("user_id") != str(user_id) or meta.get("conversation_id") != str(
            conversation_id
        ):
            raise ConversationNotFoundError()
