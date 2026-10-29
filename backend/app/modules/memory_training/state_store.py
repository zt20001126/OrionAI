"""通过 Redis 保存短期训练状态，并用乐观事务保护状态转换。"""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import TypeVar

from redis import Redis
from redis.exceptions import RedisError, WatchError

from app.modules.memory_training.constants import (
    ACTIVE_SESSION_TTL_SECONDS,
    COMPLETED_SESSION_TTL_SECONDS,
    IMAGE_LOADING_TTL_SECONDS,
    OBSERVATION_SECONDS,
    RECENT_IMAGE_TTL_SECONDS,
    SCORE_PER_QUESTION,
    SESSION_ANSWERING,
    SESSION_COMPLETED,
    SESSION_GENERATION_FAILED,
    SESSION_IMAGE_LOADING,
    SESSION_OBSERVING,
    SESSION_WAITING_QUESTIONS,
)
from app.modules.memory_training.errors import MemoryTrainingUnavailableError
from app.modules.memory_training.schemas import StoredTrainingQuestion, TrainingSessionState

_Result = TypeVar("_Result")
_MAX_TRANSACTION_ATTEMPTS = 5


class MemoryTrainingStateStore:
    """提供训练会话读写、固定 TTL、重复提交保护和图片轮换记录。"""

    def __init__(self, client: Redis, key_prefix: str = "orionai:memory-training") -> None:
        self._client = client
        self._key_prefix = key_prefix

    def create(self, state: TrainingSessionState) -> bool:
        """以短加载 TTL 创建一个全新的训练会话。"""

        try:
            return bool(
                self._client.set(
                    self._session_key(state.session_id),
                    state.model_dump_json(),
                    ex=IMAGE_LOADING_TTL_SECONDS,
                    nx=True,
                )
            )
        except RedisError:
            raise MemoryTrainingUnavailableError from None

    def get(self, session_id: str, user_id: int) -> TrainingSessionState | None:
        """读取并校验会话所有者，不区分跨用户 ID 与不存在 ID。"""

        state = self._get_any(session_id)
        if state is None or state.user_id != str(user_id):
            return None
        return state

    def get_any(self, session_id: str) -> TrainingSessionState | None:
        """供可信 Celery Worker 读取会话，不用于 API 用户授权。"""

        return self._get_any(session_id)

    def get_recent_image_id(self, user_id: int) -> int | None:
        """读取用户短期最近图片 ID，降低相邻训练重复概率。"""

        try:
            value = self._client.get(self._recent_image_key(user_id))
        except RedisError:
            raise MemoryTrainingUnavailableError from None
        return int(value) if value else None

    def set_recent_image_id(self, user_id: int, image_id: int) -> None:
        """保存短期图片轮换标记，不形成永久用户历史。"""

        try:
            self._client.set(
                self._recent_image_key(user_id), str(image_id), ex=RECENT_IMAGE_TTL_SECONDS
            )
        except RedisError:
            raise MemoryTrainingUnavailableError from None

    def start_observation(
        self, session_id: str, user_id: int
    ) -> tuple[TrainingSessionState | None, bool]:
        """原子启动 15 秒观察和题目生成；重复请求不重复投递任务。"""

        def update(
            state: TrainingSessionState,
        ) -> tuple[TrainingSessionState, bool, bool, int | None]:
            if state.state == SESSION_OBSERVING:
                return state, False, False, None
            if state.state != SESSION_IMAGE_LOADING:
                return state, False, False, None
            started_at = datetime.now(UTC)
            changed = state.model_copy(
                update={
                    "state": SESSION_OBSERVING,
                    "observation_started_at": started_at,
                    "observation_deadline_at": started_at + timedelta(seconds=OBSERVATION_SECONDS),
                }
            )
            return changed, True, True, ACTIVE_SESSION_TTL_SECONDS

        return self._mutate(session_id, user_id, update)

    def save_questions(self, session_id: str, questions: list[StoredTrainingQuestion]) -> bool:
        """只接受当前有效会话的第一份完整题集，并按观察截止时刻更新阶段。"""

        def update(
            state: TrainingSessionState,
        ) -> tuple[TrainingSessionState, bool, bool, int | None]:
            if state.state not in {SESSION_OBSERVING, SESSION_WAITING_QUESTIONS}:
                return state, False, False, None
            if state.questions or state.generation_error_code:
                return state, False, False, None
            now = datetime.now(UTC)
            next_state = (
                SESSION_ANSWERING
                if state.observation_deadline_at is not None
                and now >= state.observation_deadline_at
                else state.state
            )
            changed = state.model_copy(update={"questions": questions, "state": next_state})
            return changed, True, True, None

        updated, saved = self._mutate(session_id, None, update)
        return bool(updated is not None and saved)

    def mark_generation_failed(self, session_id: str, error_code: str) -> None:
        """记录最终出题失败，且不覆盖已经生成或提交的训练结果。"""

        def update(
            state: TrainingSessionState,
        ) -> tuple[TrainingSessionState, None, bool, int | None]:
            if state.state not in {SESSION_OBSERVING, SESSION_WAITING_QUESTIONS}:
                return state, None, False, None
            if state.questions or state.generation_error_code:
                return state, None, False, None
            now = datetime.now(UTC)
            failed_state = (
                SESSION_GENERATION_FAILED
                if state.observation_deadline_at is not None
                and now >= state.observation_deadline_at
                else state.state
            )
            return (
                state.model_copy(
                    update={"state": failed_state, "generation_error_code": error_code}
                ),
                None,
                True,
                None,
            )

        self._mutate(session_id, None, update)

    def synchronize_status(self, session_id: str, user_id: int) -> TrainingSessionState | None:
        """按服务器当前时间推进观察结束后的状态。"""

        def update(
            state: TrainingSessionState,
        ) -> tuple[TrainingSessionState, None, bool, int | None]:
            if state.state not in {SESSION_OBSERVING, SESSION_WAITING_QUESTIONS}:
                return state, None, False, None
            now = datetime.now(UTC)
            deadline = state.observation_deadline_at
            if deadline is None:
                return state, None, False, None
            if state.generation_error_code and deadline <= now:
                return (
                    state.model_copy(update={"state": SESSION_GENERATION_FAILED}),
                    None,
                    True,
                    None,
                )
            if state.questions and deadline <= now:
                return state.model_copy(update={"state": SESSION_ANSWERING}), None, True, None
            if not state.questions and not state.generation_error_code:
                if deadline <= now and state.state != SESSION_WAITING_QUESTIONS:
                    return (
                        state.model_copy(update={"state": SESSION_WAITING_QUESTIONS}),
                        None,
                        True,
                        None,
                    )
            return state, None, False, None

        updated, _ = self._mutate(session_id, user_id, update)
        return updated

    def submit_answers(
        self,
        session_id: str,
        user_id: int,
        answers: dict[str, str],
    ) -> tuple[TrainingSessionState | None, bool]:
        """原子完成判分；相同重复提交返回已保存结果，不同答案不覆盖。"""

        def update(
            state: TrainingSessionState,
        ) -> tuple[TrainingSessionState, bool, bool, int | None]:
            if state.state == SESSION_COMPLETED:
                same_answers = state.answers == answers
                return state, same_answers, False, None
            if state.state != SESSION_ANSWERING:
                return state, False, False, None
            question_ids = {question.id for question in state.questions}
            if set(answers) != question_ids:
                return state, False, False, None
            correct_count = sum(
                answers[question.id] == question.correct_option_id for question in state.questions
            )
            changed = state.model_copy(
                update={
                    "state": SESSION_COMPLETED,
                    "answers": answers,
                    "score": correct_count * SCORE_PER_QUESTION,
                    "correct_count": correct_count,
                    "completed_at": datetime.now(UTC),
                }
            )
            return changed, True, True, COMPLETED_SESSION_TTL_SECONDS

        return self._mutate(session_id, user_id, update)

    def _get_any(self, session_id: str) -> TrainingSessionState | None:
        try:
            raw_state = self._client.get(self._session_key(session_id))
        except RedisError:
            raise MemoryTrainingUnavailableError from None
        if raw_state is None:
            return None
        try:
            return TrainingSessionState.model_validate_json(raw_state)
        except ValueError:
            raise MemoryTrainingUnavailableError from None

    def _mutate(
        self,
        session_id: str,
        user_id: int | None,
        update: Callable[
            [TrainingSessionState], tuple[TrainingSessionState, _Result, bool, int | None]
        ],
    ) -> tuple[TrainingSessionState | None, _Result | None]:
        """使用 WATCH/MULTI 保证多实例下的状态转换不互相覆盖。"""

        key = self._session_key(session_id)
        try:
            for _ in range(_MAX_TRANSACTION_ATTEMPTS):
                with self._client.pipeline() as pipeline:
                    try:
                        pipeline.watch(key)
                        raw_state = pipeline.get(key)
                        if raw_state is None:
                            return None, None
                        state = TrainingSessionState.model_validate_json(raw_state)
                        if user_id is not None and state.user_id != str(user_id):
                            return None, None
                        changed_state, result, changed, new_ttl = update(state)
                        if not changed:
                            return state, result
                        remaining_ttl = pipeline.pttl(key) if new_ttl is None else new_ttl * 1000
                        if remaining_ttl <= 0:
                            return None, None
                        pipeline.multi()
                        pipeline.set(key, changed_state.model_dump_json(), px=remaining_ttl)
                        pipeline.execute()
                        return changed_state, result
                    except WatchError:
                        continue
        except RedisError:
            raise MemoryTrainingUnavailableError from None
        except ValueError:
            raise MemoryTrainingUnavailableError from None
        raise MemoryTrainingUnavailableError("训练状态更新冲突，请重试。")

    def _session_key(self, session_id: str) -> str:
        return f"{self._key_prefix}:session:{session_id}"

    def _recent_image_key(self, user_id: int) -> str:
        return f"{self._key_prefix}:last-image:{user_id}"
