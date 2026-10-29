"""编排记忆训练会话、图片抽取、服务端计时和确定性判分。"""

import logging
from collections.abc import Callable
from datetime import UTC, datetime

from redis import Redis
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.infrastructure.database.snowflake import generate_snowflake_id
from app.modules.auth.models import User
from app.modules.memory_training import repository
from app.modules.memory_training.constants import (
    GENERATION_ERROR_QUEUE,
    MAX_SCORE,
    MEMORY_TRAINING_SKILL_CODE,
    MEMORY_TRAINING_SKILL_NAME,
    OBSERVATION_SECONDS,
    QUESTION_COUNT,
    SCORE_PER_QUESTION,
    SESSION_ANSWERING,
    SESSION_COMPLETED,
    SESSION_GENERATION_FAILED,
    SESSION_IMAGE_LOADING,
    SESSION_OBSERVING,
    SESSION_WAITING_QUESTIONS,
)
from app.modules.memory_training.errors import (
    MemoryTrainingConflictError,
    MemoryTrainingNotFoundError,
    MemoryTrainingUnavailableError,
    MemoryTrainingValidationError,
)
from app.modules.memory_training.schemas import (
    ObservationStartedResponse,
    PreparationResponse,
    PublicQuestion,
    QuestionReview,
    QuestionsResponse,
    SessionCreatedResponse,
    SessionStatusResponse,
    StoredTrainingQuestion,
    SubmissionSummaryResponse,
    TrainingResultResponse,
    TrainingSessionState,
)
from app.modules.memory_training.state_store import MemoryTrainingStateStore
from app.modules.skills import repository as skills_repository

logger = logging.getLogger(__name__)


class MemoryTrainingService:
    """执行记忆训练业务流程，协调 SQLAlchemy、Redis 和 Celery 投递。"""

    def __init__(
        self,
        *,
        session: Session,
        redis_client: Redis,
        dispatch_question_generation: Callable[[str], None],
    ) -> None:
        self._session = session
        self._state_store = MemoryTrainingStateStore(redis_client)
        self._dispatch_question_generation = dispatch_question_generation

    def preparation(self, current_user: User) -> PreparationResponse:
        """返回训练规则，不读取或返回任何训练图片。"""

        self._require_skill(current_user.id)
        return PreparationResponse(
            tool_name=MEMORY_TRAINING_SKILL_NAME,
            description="通过观察图片并回答细节问题，练习视觉注意力与记忆能力。",
            observation_seconds=OBSERVATION_SECONDS,
            question_count=QUESTION_COUNT,
            score_per_question=SCORE_PER_QUESTION,
            max_score=MAX_SCORE,
        )

    def create_session(self, current_user: User) -> SessionCreatedResponse:
        """抽取启用图片并创建两分钟有效的图片加载会话。

        Step 1: 确认当前用户已添加且仍可使用记忆训练工具。
        Step 2: 优先避开该用户最近抽到的图片，从 Repository 选择启用素材。
        Step 3: 将最少会话数据写入 Redis，并设置图片加载阶段 TTL。
        """

        self._require_skill(current_user.id)
        previous_image_id = self._state_store.get_recent_image_id(current_user.id)
        try:
            image = repository.pick_random_enabled_image(
                self._session,
                excluded_image_id=previous_image_id,
            )
        except SQLAlchemyError:
            self._session.rollback()
            raise MemoryTrainingUnavailableError from None
        if image is None:
            raise MemoryTrainingUnavailableError(
                "训练图片暂不可用，请稍后重试。", code="MEMORY_TRAINING_NO_ENABLED_IMAGES"
            )

        session_id = str(generate_snowflake_id())
        state = TrainingSessionState(
            session_id=session_id,
            user_id=str(current_user.id),
            image_url=image.image_url,
            state=SESSION_IMAGE_LOADING,
        )
        if not self._state_store.create(state):
            raise MemoryTrainingUnavailableError
        self._state_store.set_recent_image_id(current_user.id, image.id)
        return SessionCreatedResponse(
            session_id=session_id,
            state=SESSION_IMAGE_LOADING,
            image_url=image.image_url,
        )

    def start_observation(self, current_user: User, session_id: str) -> ObservationStartedResponse:
        """以服务端时间启动观察窗口，并至多投递一次出题任务。"""

        self._require_skill(current_user.id)
        state, should_dispatch = self._state_store.start_observation(session_id, current_user.id)
        if state is None:
            raise MemoryTrainingNotFoundError
        if state.state != SESSION_OBSERVING or state.observation_started_at is None:
            raise MemoryTrainingConflictError("当前会话无法开始观察。")
        if should_dispatch:
            try:
                self._dispatch_question_generation(session_id)
            except Exception:
                logger.exception("memory_training_task_dispatch_failed session_id=%s", session_id)
                self._state_store.mark_generation_failed(session_id, GENERATION_ERROR_QUEUE)

        deadline = state.observation_deadline_at
        if deadline is None:
            raise MemoryTrainingUnavailableError
        remaining_ms = max(0, int((deadline - datetime.now(UTC)).total_seconds() * 1000))
        return ObservationStartedResponse(
            session_id=session_id,
            state=SESSION_OBSERVING,
            observation_started_at=state.observation_started_at,
            observation_deadline_at=deadline,
            remaining_ms=remaining_ms,
        )

    def get_status(self, current_user: User, session_id: str) -> SessionStatusResponse:
        """读取本人训练状态，并依据服务端时钟推进观察结束阶段。"""

        state = self._state_store.synchronize_status(session_id, current_user.id)
        if state is None:
            raise MemoryTrainingNotFoundError
        remaining_ms = self._remaining_ms(state)
        image_url = (
            state.image_url if state.state in {SESSION_IMAGE_LOADING, SESSION_OBSERVING} else None
        )
        questions_ready = state.state == SESSION_ANSWERING
        return SessionStatusResponse(
            session_id=session_id,
            state=state.state,
            remaining_ms=remaining_ms,
            questions_ready=questions_ready,
            image_url=image_url,
            error_code=(
                state.generation_error_code if state.state == SESSION_GENERATION_FAILED else None
            ),
        )

    def get_questions(self, current_user: User, session_id: str) -> QuestionsResponse:
        """只在服务端观察时间结束且题目就绪时投影公开题目 DTO。"""

        state = self._state_store.synchronize_status(session_id, current_user.id)
        if state is None:
            raise MemoryTrainingNotFoundError
        if state.state != SESSION_ANSWERING:
            self._raise_state_conflict(state)
        return QuestionsResponse(
            questions=[
                PublicQuestion(
                    id=question.id,
                    prompt=question.prompt,
                    options=question.options,
                )
                for question in state.questions
            ]
        )

    def submit_answers(
        self,
        current_user: User,
        session_id: str,
        answers: dict[str, str],
    ) -> SubmissionSummaryResponse:
        """校验完整答案并由 Redis 原子转换保证判分幂等。

        Step 1: 确认答案题目 ID 与服务端题集完全一致。
        Step 2: 校验每个选项确实属于对应题目。
        Step 3: 原子保存答案、总分和正确题数；重复提交无法修改已完成结果。
        """

        state = self._state_store.get(session_id, current_user.id)
        if state is None:
            raise MemoryTrainingNotFoundError
        expected_ids = {question.id for question in state.questions}
        if set(answers) != expected_ids:
            raise MemoryTrainingValidationError("请回答全部五道题后再提交。")
        question_by_id = {question.id: question for question in state.questions}
        for question_id, option_id in answers.items():
            if option_id not in {option.id for option in question_by_id[question_id].options}:
                raise MemoryTrainingValidationError("所选选项不属于当前题目。")

        final_state, accepted = self._state_store.submit_answers(
            session_id, current_user.id, answers
        )
        if final_state is None:
            raise MemoryTrainingNotFoundError
        if not accepted:
            if final_state.state == SESSION_COMPLETED:
                raise MemoryTrainingConflictError(
                    "训练已提交，不能修改答案。", code="MEMORY_TRAINING_ALREADY_SUBMITTED"
                )
            self._raise_state_conflict(final_state)
        return SubmissionSummaryResponse(
            state=SESSION_COMPLETED,
            score=final_state.score or 0,
            correct_count=final_state.correct_count or 0,
            question_count=QUESTION_COUNT,
        )

    def get_result(self, current_user: User, session_id: str) -> TrainingResultResponse:
        """读取本人已完成结果及固定在会话中的原图链接。"""

        state = self._state_store.get(session_id, current_user.id)
        if state is None:
            raise MemoryTrainingNotFoundError
        if state.state != SESSION_COMPLETED or state.answers is None:
            raise MemoryTrainingConflictError(
                "训练尚未完成，暂时没有结果。", code="MEMORY_TRAINING_RESULT_NOT_READY"
            )
        reviews = [
            self._question_review(question, state.answers[question.id])
            for question in state.questions
        ]
        score = state.score or 0
        correct_count = state.correct_count or 0
        return TrainingResultResponse(
            session_id=session_id,
            score=score,
            correct_count=correct_count,
            incorrect_count=QUESTION_COUNT - correct_count,
            correct_rate=correct_count / QUESTION_COUNT,
            image_url=state.image_url,
            questions=reviews,
        )

    def _require_skill(self, user_id: int) -> None:
        """只有已添加且仍发布的技能允许启动和操作训练。"""

        try:
            has_skill = skills_repository.user_has_skill_code(
                self._session, user_id, MEMORY_TRAINING_SKILL_CODE
            )
        except SQLAlchemyError:
            self._session.rollback()
            raise MemoryTrainingUnavailableError from None
        if not has_skill:
            raise MemoryTrainingConflictError(
                "请先在技能市场添加记忆训练。", code="MEMORY_TRAINING_SKILL_NOT_ADDED"
            )

    @staticmethod
    def _remaining_ms(state: TrainingSessionState) -> int:
        if state.state != SESSION_OBSERVING or state.observation_deadline_at is None:
            return 0
        return max(
            0,
            int((state.observation_deadline_at - datetime.now(UTC)).total_seconds() * 1000),
        )

    @staticmethod
    def _raise_state_conflict(state: TrainingSessionState) -> None:
        if state.state == SESSION_GENERATION_FAILED:
            raise MemoryTrainingConflictError(
                "本次出题失败，请重新开始训练。",
                code=state.generation_error_code or "MEMORY_TRAINING_QUESTION_FAILED",
            )
        if state.state in {SESSION_OBSERVING, SESSION_IMAGE_LOADING}:
            raise MemoryTrainingConflictError(
                "观察时间尚未结束，暂时不能获取题目。",
                code="MEMORY_TRAINING_OBSERVATION_NOT_FINISHED",
            )
        if state.state == SESSION_WAITING_QUESTIONS:
            raise MemoryTrainingConflictError(
                "正在准备记忆测试，请稍候。", code="MEMORY_TRAINING_QUESTIONS_NOT_READY"
            )
        raise MemoryTrainingConflictError("当前训练状态不能进行此操作。")

    @staticmethod
    def _question_review(question: StoredTrainingQuestion, user_option_id: str) -> QuestionReview:
        """将内部答案转换成提交后的单题复盘 DTO。"""

        option_by_id = {option.id: option.text for option in question.options}
        is_correct = user_option_id == question.correct_option_id
        return QuestionReview(
            id=question.id,
            prompt=question.prompt,
            user_option_id=user_option_id,
            user_option_text=option_by_id[user_option_id],
            correct_option_id=question.correct_option_id,
            correct_option_text=option_by_id[question.correct_option_id],
            is_correct=is_correct,
            score=SCORE_PER_QUESTION if is_correct else 0,
            explanation=question.explanation,
        )
