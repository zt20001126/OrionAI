import asyncio
import json

import pytest

from app.infrastructure.redis.conversation_run_store import ConversationRunStore
from app.modules.conversations.models.models import Conversation
from app.modules.conversations.service.run_coordinator import ConversationRunCoordinator
from app.modules.conversations.service.service import PreparedConversationTurn


class MemoryRedis:
    """为 Redis 任务存储提供确定性的内存替身。"""

    def __init__(self) -> None:
        self.hashes: dict[str, dict[str, str]] = {}
        self.values: dict[str, str] = {}
        self.streams: dict[str, list[tuple[str, dict[str, str]]]] = {}
        self.sequence = 0

    def eval(self, script: str, key_count: int, *args: object) -> int:
        keys = [str(item) for item in args[:key_count]]
        values = [str(item) for item in args[key_count:]]
        if key_count == 3:
            if keys[0] in self.values:
                return 0
            self.hashes[keys[1]] = {
                "user_id": values[0],
                "conversation_id": values[1],
                "status": "running",
            }
            self.values[keys[0]] = values[2]
            return 1
        if "HGET" in script:
            metadata = self.hashes.get(keys[0], {})
            if metadata.get("status") != "running":
                return 0
            metadata["status"] = "interrupt_requested"
            return 1
        if self.values.get(keys[0]) == values[0]:
            self.values.pop(keys[0], None)
        return 1

    def xadd(self, key: str, values: dict[str, str]) -> str:
        self.sequence += 1
        event_id = f"{self.sequence}-0"
        self.streams.setdefault(key, []).append((event_id, values))
        return event_id

    def hset(self, key: str, field: str, value: str) -> None:
        self.hashes.setdefault(key, {})[field] = value

    def hgetall(self, key: str) -> dict[str, str]:
        return self.hashes.get(key, {}).copy()

    def get(self, key: str) -> str | None:
        return self.values.get(key)

    def expire(self, _key: str, _seconds: int) -> None:
        return

    def close(self) -> None:
        return

    def xrange(self, key: str, min: str, count: int) -> list[tuple[str, dict[str, str]]]:
        cursor = min.removeprefix("(")
        rows = self.streams.get(key, [])
        return [(event_id, values) for event_id, values in rows if event_id > cursor][:count]


def test_run_store_replays_events_and_tracks_interrupt_state() -> None:
    redis = MemoryRedis()
    store = ConversationRunStore(redis)  # type: ignore[arg-type]
    store.create("run-1", 10, 20)

    store.append("run-1", {"type": "text_delta", "content": "你好"})
    assert store.events("run-1") == [("1-0", {"type": "text_delta", "content": "你好"})]
    assert store.active(10, 20) == "run-1"

    assert store.request_interrupt("run-1") is True
    assert store.get("run-1")["status"] == "interrupt_requested"
    store.set_status("run-1", "interrupted")

    assert store.active(10, 20) is None
    assert (
        json.loads(redis.streams[store._events_key("run-1")][0][1]["payload"])["content"] == "你好"
    )


@pytest.mark.anyio
async def test_coordinator_runs_without_listener_and_replays_after_completion() -> None:
    redis = MemoryRedis()
    coordinator = ConversationRunCoordinator(redis)  # type: ignore[arg-type]

    class CompletedService:
        async def execute_background_run(self, _prepared, run_store, run_id: str) -> None:
            run_store.append(run_id, {"type": "text_delta", "content": "完成"})

    conversation = Conversation(id=20, user_id=10, skill_code="general_chat")
    prepared = PreparedConversationTurn(
        user_id=10,
        conversation=conversation,
        message_text="问题",
        message_id=30,
        should_generate_title=False,
    )
    run_id = coordinator.start(CompletedService(), prepared)  # type: ignore[arg-type]
    for _ in range(20):
        if coordinator.active(10, 20) is None:
            break
        await asyncio.sleep(0.01)

    events = [event async for event in coordinator.listen(run_id, 10, 20)]
    assert [event.data for event in events] == [
        {"type": "text_delta", "content": "完成"},
        {"type": "run_status", "status": "completed"},
    ]
    await coordinator.close()


@pytest.mark.anyio
async def test_coordinator_interrupt_stops_the_run_task() -> None:
    redis = MemoryRedis()
    coordinator = ConversationRunCoordinator(redis)  # type: ignore[arg-type]
    started = asyncio.Event()

    class BlockingService:
        async def execute_background_run(self, _prepared, _run_store, _run_id: str) -> None:
            started.set()
            await asyncio.Event().wait()

    prepared = PreparedConversationTurn(
        user_id=10,
        conversation=Conversation(id=20, user_id=10, skill_code="general_chat"),
        message_text="需要中断",
        message_id=31,
        should_generate_title=False,
    )
    run_id = coordinator.start(BlockingService(), prepared)  # type: ignore[arg-type]
    await started.wait()
    coordinator.interrupt(run_id, 10, 20)
    for _ in range(20):
        if coordinator._store.get(run_id).get("status") == "interrupted":
            break
        await asyncio.sleep(0.01)

    assert coordinator._store.get(run_id)["status"] == "interrupted"
    await coordinator.close()
