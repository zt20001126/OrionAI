"""编排会话权限范围、消息持久化和 BaseAgent 调用。"""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import partial

import anyio
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.agent.errors import AgentError, AgentInputError
from app.agent.memory.thread import build_conversation_thread_id
from app.agent.runtime.base_agent import invoke_agent_from_worker_thread
from app.agent.runtime.protocol import AgentRuntime
from app.agent.schemas import (
    AgentRequest,
    AgentResponse,
    AgentStreamResult,
    AgentTextDelta,
    QuestionPayload,
)
from app.modules.auth.models import User
from app.modules.conversations import repository
from app.modules.conversations.errors import (
    ConversationConflictError,
    ConversationNotFoundError,
    ConversationUnavailableError,
    ConversationValidationError,
)
from app.modules.conversations.models import Conversation, Message
from app.modules.conversations.schemas import (
    AgentTurnResponse,
    ConversationCreateResponse,
    ConversationListResponse,
    ConversationQuestionEvent,
    ConversationTextDeltaEvent,
    MessageContent,
    MessageListResponse,
    MessageResponse,
    QuestionAnswersRequest,
    QuestionContentPart,
)
from app.modules.conversations.title import (
    ConversationTitleGenerator,
    fallback_conversation_title,
)
from app.modules.image_generation.constants import IMAGE_RESULT_URL_PREFIX
from app.modules.skills import repository as skills_repository
from app.shared.streaming import EventType, StreamEvent

logger = logging.getLogger(__name__)
MAX_PAGE_SIZE = 100
DEFAULT_PAGE_SIZE = 50


@dataclass(frozen=True)
class PreparedConversationTurn:
    """流式响应开始前已校验并保存用户消息的一轮对话。"""

    user_id: int
    conversation: Conversation
    message_text: str
    message_id: int
    should_generate_title: bool
    resume_answers: dict[str, str] | None = None


class ConversationService:
    """实现当前用户的对话数据访问和 Agent 对话闭环。"""

    def __init__(
        self,
        *,
        session: Session,
        agent: AgentRuntime | None,
        title_generator: ConversationTitleGenerator | None = None,
        agent_registry: dict[str, AgentRuntime] | None = None,
    ) -> None:
        self._session = session
        self._agents = dict(agent_registry or {})
        if agent is not None:
            self._agents.setdefault(skills_repository.GENERAL_CHAT_SKILL_CODE, agent)
        self._title_generator = title_generator

    def create_conversation(
        self,
        user: User,
        *,
        skill_code: str = skills_repository.GENERAL_CHAT_SKILL_CODE,
    ) -> ConversationCreateResponse:
        """创建一个无标题的新会话。"""

        try:
            self._require_skill(user.id, skill_code)
            if skill_code not in self._agents:
                raise ConversationConflictError("该技能当前没有可用的智能体运行入口。")
            conversation = repository.create_conversation(self._session, user.id, skill_code)
            self._session.commit()
            self._session.refresh(conversation)
            return self._conversation_response(conversation)
        except SQLAlchemyError:
            self._session.rollback()
            raise ConversationUnavailableError from None

    def list_conversations(
        self,
        user: User,
        *,
        limit: int = DEFAULT_PAGE_SIZE,
        offset: int = 0,
    ) -> ConversationListResponse:
        """只列出当前用户会话，限制单页最大记录数。"""

        self._validate_pagination(limit, offset)
        try:
            conversations = repository.list_conversations(
                self._session,
                user.id,
                limit=limit,
                offset=offset,
            )
        except SQLAlchemyError:
            self._session.rollback()
            raise ConversationUnavailableError from None
        return ConversationListResponse(
            items=[self._conversation_response(conversation) for conversation in conversations],
            limit=limit,
            offset=offset,
        )

    def list_messages(
        self,
        user: User,
        conversation_id: int,
        *,
        limit: int = DEFAULT_PAGE_SIZE,
        offset: int = 0,
    ) -> MessageListResponse:
        """验证会话所有权后按 ID 升序返回消息。"""

        self._validate_pagination(limit, offset)
        try:
            conversation = self._get_conversation(user.id, conversation_id)
            messages = repository.list_messages(
                self._session,
                conversation.id,
                limit=limit,
                offset=offset,
            )
        except SQLAlchemyError:
            self._session.rollback()
            raise ConversationUnavailableError from None
        return MessageListResponse(
            items=[self._message_response(message) for message in messages],
            skill_code=conversation.skill_code,
            limit=limit,
            offset=offset,
        )

    def send_message(
        self,
        user: User,
        conversation_id: int,
        message_text: str,
    ) -> AgentTurnResponse:
        """保存用户文本，运行 Agent，并保存助手文本或题卡。"""

        prepared = self._prepare_message_turn(user, conversation_id, message_text)
        if prepared.should_generate_title:
            agent_response = self._invoke_agent_and_title(
                user_id=prepared.user_id,
                conversation=prepared.conversation,
                message_text=prepared.message_text,
                message_id=prepared.message_id,
                resume_answers=prepared.resume_answers,
            )
        else:
            agent_response = self._invoke_agent(
                user_id=prepared.user_id,
                conversation_id=prepared.conversation.id,
                message_text=prepared.message_text,
                message_id=prepared.message_id,
                skill_code=prepared.conversation.skill_code,
                resume_answers=prepared.resume_answers,
            )
        return self._save_agent_response(prepared.conversation, agent_response)

    def answer_questions(
        self,
        user: User,
        conversation_id: int,
        request: QuestionAnswersRequest,
    ) -> AgentTurnResponse:
        """验证当前待答题卡并在原 Checkpointer 线程继续运行。"""

        prepared = self._prepare_answer_turn(user, conversation_id, request)
        agent_response = self._invoke_agent(
            user_id=prepared.user_id,
            conversation_id=prepared.conversation.id,
            message_text=prepared.message_text,
            message_id=prepared.message_id,
            skill_code=prepared.conversation.skill_code,
            resume_answers=prepared.resume_answers,
        )
        return self._save_agent_response(prepared.conversation, agent_response)

    def prepare_message_stream(
        self,
        user: User,
        conversation_id: int,
        message_text: str,
    ) -> PreparedConversationTurn:
        """在 SSE 响应头发送前完成普通消息的业务校验和用户消息写入。"""

        return self._prepare_message_turn(user, conversation_id, message_text)

    def prepare_answer_stream(
        self,
        user: User,
        conversation_id: int,
        request: QuestionAnswersRequest,
    ) -> PreparedConversationTurn:
        """在 SSE 响应头发送前校验题卡并保存用户答案。"""

        return self._prepare_answer_turn(user, conversation_id, request)

    async def stream_turn(
        self,
        prepared: PreparedConversationTurn,
    ) -> AsyncIterator[StreamEvent]:
        """将 Agent 文本增量转为 SSE 消息，并在成功后保存正式结果。"""

        agent = self._runtime_for(prepared.conversation)
        if agent is None:
            raise ConversationUnavailableError

        title_task = (
            asyncio.create_task(self._title_generator.generate_title(prepared.message_text))
            if prepared.should_generate_title and self._title_generator is not None
            else None
        )
        agent_response: AgentResponse | None = None
        thread_id = build_conversation_thread_id(
            prepared.user_id, prepared.conversation.id, prepared.conversation.skill_code
        )
        try:
            async for event in agent.astream(
                AgentRequest(message=prepared.message_text),
                runnable_config=self._runnable_config(prepared, thread_id),
                message_id=str(prepared.message_id),
            ):
                if isinstance(event, AgentTextDelta):
                    payload = ConversationTextDeltaEvent(
                        type="text_delta",
                        content=event.content,
                    )
                    yield StreamEvent(
                        event_type=EventType.MESSAGE,
                        data=payload.model_dump(mode="json"),
                    )
                elif isinstance(event, AgentStreamResult):
                    agent_response = event.response

            if agent_response is None:
                raise ConversationUnavailableError

            await self._finish_stream_title(prepared, title_task)
            persisted_turn = await anyio.to_thread.run_sync(
                self._save_stream_response,
                prepared,
                agent_response,
            )
        except asyncio.CancelledError:
            if title_task is not None:
                title_task.cancel()
                with suppress(asyncio.CancelledError, Exception):
                    await title_task
            with anyio.CancelScope(shield=True):
                with suppress(Exception):
                    await self._finish_stream_title(prepared, None)
            raise
        except Exception as error:
            await self._finish_stream_title(prepared, title_task)
            self._raise_agent_error(error)

        if persisted_turn.status == "waiting":
            payload = ConversationQuestionEvent(
                type="question",
                message=persisted_turn.message,
            )
            yield StreamEvent(
                event_type=EventType.MESSAGE,
                data=payload.model_dump(mode="json"),
            )

    def _prepare_message_turn(
        self,
        user: User,
        conversation_id: int,
        message_text: str,
    ) -> PreparedConversationTurn:
        """校验普通消息并按现有顺序先提交用户消息。"""

        conversation = self._get_conversation_safely(
            user.id,
            conversation_id,
            for_update=True,
        )
        self._require_skill(user.id, conversation.skill_code)
        self._ensure_not_waiting(conversation.id)
        try:
            should_generate_title = (
                not conversation.title or not conversation.title.strip()
            ) and not repository.has_messages(self._session, conversation.id)
        except SQLAlchemyError:
            self._session.rollback()
            raise ConversationUnavailableError from None
        user_message = self._save_user_message(conversation, message_text)
        return PreparedConversationTurn(
            user_id=user.id,
            conversation=conversation,
            message_text=message_text,
            message_id=user_message.id,
            should_generate_title=should_generate_title,
        )

    def _prepare_answer_turn(
        self,
        user: User,
        conversation_id: int,
        request: QuestionAnswersRequest,
    ) -> PreparedConversationTurn:
        """校验题卡答案并按现有顺序先提交用户选择。"""

        conversation = self._get_conversation_safely(user.id, conversation_id)
        self._require_skill(user.id, conversation.skill_code)
        latest_message = self._get_latest_message_safely(conversation.id)
        question_payload = self._pending_questions(latest_message)
        try:
            question_payload.validate_answers(request.answers)
        except ValueError as error:
            raise ConversationValidationError(str(error)) from None

        answer_text = self._format_answer(question_payload, request)
        user_message = self._save_user_message(conversation, answer_text)
        return PreparedConversationTurn(
            user_id=user.id,
            conversation=conversation,
            message_text=answer_text,
            message_id=user_message.id,
            should_generate_title=False,
            resume_answers=request.answers,
        )

    async def _finish_stream_title(
        self,
        prepared: PreparedConversationTurn,
        title_task: asyncio.Task[str | None] | None,
    ) -> None:
        """收束并保存首轮标题；标题生成失败时写入首条消息回退值。"""

        if not prepared.should_generate_title:
            return

        generated_title = None
        if title_task is not None:
            try:
                generated_title = await title_task
            except asyncio.CancelledError:
                title_task.cancel()
                with suppress(asyncio.CancelledError, Exception):
                    await title_task
                await self._persist_stream_title(prepared, None)
                raise
            except Exception as error:
                logger.warning(
                    "conversation_title_task_failed error_type=%s",
                    type(error).__name__,
                )

        await self._persist_stream_title(prepared, generated_title)

    async def _persist_stream_title(
        self,
        prepared: PreparedConversationTurn,
        generated_title: str | None,
    ) -> None:
        """在取消屏蔽区完成标题保存，避免丢失首轮标题回退。"""

        with anyio.CancelScope(shield=True):
            await anyio.to_thread.run_sync(
                partial(
                    self._save_conversation_title,
                    user_id=prepared.user_id,
                    conversation_id=prepared.conversation.id,
                    first_user_message=prepared.message_text,
                    generated_title=generated_title,
                )
            )

    def _save_stream_response(
        self,
        prepared: PreparedConversationTurn,
        response: AgentResponse,
    ) -> AgentTurnResponse:
        """保存流式执行的正式助手结果。"""

        return self._save_agent_response(prepared.conversation, response)

    def _invoke_agent(
        self,
        *,
        user_id: int,
        conversation_id: int,
        message_text: str,
        message_id: int,
        skill_code: str,
        resume_answers: dict[str, str] | None,
    ) -> AgentResponse:
        """通过技能对应的 Runtime 调度 LangGraph，并映射运行错误。"""

        agent = self._agents.get(skill_code)
        if agent is None:
            raise ConversationUnavailableError
        thread_id = build_conversation_thread_id(user_id, conversation_id, skill_code)
        configurable: dict[str, object] = {"thread_id": thread_id}
        if skill_code in {"image_agent", "resume_assistant"}:
            configurable.update(
                {
                    "user_id": user_id,
                    "conversation_id": conversation_id,
                    "run_id": str(message_id),
                }
            )
            if resume_answers is not None:
                configurable["resume_answers"] = resume_answers
        try:
            return invoke_agent_from_worker_thread(
                agent,
                AgentRequest(message=message_text),
                runnable_config={"configurable": configurable},
                message_id=str(message_id),
            )
        except AgentInputError as error:
            raise ConversationValidationError(str(error)) from None
        except AgentError as error:
            logger.warning("conversation_agent_failed error_type=%s", type(error).__name__)
            raise ConversationUnavailableError from None
        except Exception as error:
            logger.warning("conversation_agent_bridge_failed error_type=%s", type(error).__name__)
            raise ConversationUnavailableError from None

    def _invoke_agent_and_title(
        self,
        *,
        user_id: int,
        conversation: Conversation,
        message_text: str,
        message_id: int,
        resume_answers: dict[str, str] | None = None,
    ) -> AgentResponse:
        """并行运行首轮标题与 Agent；标题失败不改变对话结果。"""

        agent = self._runtime_for(conversation)
        if agent is None:
            raise ConversationUnavailableError
        thread_id = build_conversation_thread_id(user_id, conversation.id, conversation.skill_code)
        request = AgentRequest(message=message_text)
        configurable: dict[str, object] = {
            "thread_id": thread_id,
        }
        if conversation.skill_code in {"image_agent", "resume_assistant"}:
            configurable.update(
                {
                    "user_id": user_id,
                    "conversation_id": conversation.id,
                    "run_id": str(message_id),
                }
            )
            if resume_answers is not None:
                configurable["resume_answers"] = resume_answers
        runnable_config = {"configurable": configurable}

        async def invoke_concurrently() -> tuple[
            AgentResponse | None,
            str | None,
            Exception | None,
        ]:
            title_task = (
                asyncio.create_task(self._title_generator.generate_title(message_text))
                if self._title_generator is not None
                else None
            )
            try:
                response = await agent.ainvoke(
                    request,
                    runnable_config=runnable_config,
                    message_id=str(message_id),
                )
                agent_error = None
            except Exception as error:
                response = None
                agent_error = error

            generated_title = None
            if title_task is not None:
                try:
                    generated_title = await title_task
                except Exception as error:
                    logger.warning(
                        "conversation_title_task_failed error_type=%s",
                        type(error).__name__,
                    )
            return response, generated_title, agent_error

        try:
            response, generated_title, agent_error = anyio.from_thread.run(invoke_concurrently)
        except Exception as error:
            response, generated_title, agent_error = None, None, error

        self._save_conversation_title(
            user_id=user_id,
            conversation_id=conversation.id,
            first_user_message=message_text,
            generated_title=generated_title,
        )
        if agent_error is not None:
            self._raise_agent_error(agent_error)
        if response is None:
            raise ConversationUnavailableError
        return response

    def _save_conversation_title(
        self,
        *,
        user_id: int,
        conversation_id: int,
        first_user_message: str,
        generated_title: str | None,
    ) -> None:
        """保存模型标题或首条消息回退；数据库错误不影响 Agent 回复。"""

        title = generated_title or fallback_conversation_title(first_user_message)
        try:
            repository.set_conversation_title_if_empty(
                self._session,
                user_id=user_id,
                conversation_id=conversation_id,
                title=title,
            )
            self._session.commit()
        except SQLAlchemyError:
            self._session.rollback()
            logger.warning(
                "conversation_title_save_failed conversation_id=%s",
                conversation_id,
            )

    @staticmethod
    def _raise_agent_error(error: Exception) -> None:
        """将 Agent 错误转换为稳定的会话 API 错误。"""

        if isinstance(error, AgentInputError):
            raise ConversationValidationError(str(error)) from None
        if isinstance(error, AgentError):
            logger.warning("conversation_agent_failed error_type=%s", type(error).__name__)
            raise ConversationUnavailableError from None
        logger.warning("conversation_agent_bridge_failed error_type=%s", type(error).__name__)
        raise ConversationUnavailableError from None

    def _save_agent_response(
        self,
        conversation: Conversation,
        response: AgentResponse,
    ) -> AgentTurnResponse:
        """保存用户可见的助手结果并更新最近活动时间。"""

        if response.status == "completed":
            if response.answer is None or not response.answer.strip():
                raise ConversationUnavailableError
            parts: list[dict[str, object]] = [{"type": "text", "text": response.answer}]
            if response.image_result_id is not None:
                parts.append(
                    {
                        "type": "image_result",
                        "task_result_id": response.image_result_id,
                        "generation_status": "succeeded",
                        "image_url": (
                            f"{IMAGE_RESULT_URL_PREFIX}/{response.image_result_id}/image"
                        ),
                    }
                )
            content: dict[str, object] = {"parts": parts}
        else:
            if response.questions is None:
                raise ConversationUnavailableError
            question_part = QuestionContentPart.from_payload(response.questions)
            content = {"parts": [question_part.model_dump(mode="json")]}

        try:
            assistant_message = repository.create_message(
                self._session,
                conversation_id=conversation.id,
                role="assistant",
                content=content,
            )
            repository.update_conversation_timestamp(conversation, datetime.now(UTC))
            self._session.commit()
            self._session.refresh(assistant_message)
        except SQLAlchemyError:
            self._session.rollback()
            raise ConversationUnavailableError from None

        return AgentTurnResponse(
            status=response.status,
            message=self._message_response(assistant_message),
        )

    def _save_user_message(
        self,
        conversation: Conversation,
        message_text: str,
    ) -> Message:
        """先提交用户消息，使其 ID 可作为 LangGraph 消息稳定标识。"""

        try:
            user_message = repository.create_message(
                self._session,
                conversation_id=conversation.id,
                role="user",
                content={"parts": [{"type": "text", "text": message_text}]},
            )
            repository.update_conversation_timestamp(conversation, datetime.now(UTC))
            self._session.commit()
            self._session.refresh(user_message)
            return user_message
        except SQLAlchemyError:
            self._session.rollback()
            raise ConversationUnavailableError from None

    def _get_conversation(
        self,
        user_id: int,
        conversation_id: int,
        *,
        for_update: bool = False,
    ) -> Conversation:
        conversation = repository.get_conversation(
            self._session,
            user_id,
            conversation_id,
            for_update=for_update,
        )
        if conversation is None:
            raise ConversationNotFoundError
        return conversation

    def _get_conversation_safely(
        self,
        user_id: int,
        conversation_id: int,
        *,
        for_update: bool = False,
    ) -> Conversation:
        try:
            return self._get_conversation(
                user_id,
                conversation_id,
                for_update=for_update,
            )
        except SQLAlchemyError:
            self._session.rollback()
            raise ConversationUnavailableError from None

    def _require_skill(self, user_id: int, skill_code: str) -> None:
        """只有已添加且仍发布的会话技能才可运行。"""

        try:
            is_added = skills_repository.user_has_skill_code(
                self._session,
                user_id,
                skill_code,
            )
        except SQLAlchemyError:
            self._session.rollback()
            raise ConversationUnavailableError from None
        if not is_added:
            self._session.rollback()
            raise ConversationConflictError("请先将此助手添加到我的技能后再使用。")

    def _ensure_not_waiting(self, conversation_id: int) -> None:
        latest_message = self._get_latest_message_safely(conversation_id)
        if self._message_has_question(latest_message):
            raise ConversationConflictError("请先提交当前题卡答案，再发送新消息。")

    def _get_latest_message_safely(self, conversation_id: int) -> Message | None:
        try:
            return repository.get_latest_message(self._session, conversation_id)
        except SQLAlchemyError:
            self._session.rollback()
            raise ConversationUnavailableError from None

    @classmethod
    def _pending_questions(cls, message: Message | None) -> QuestionPayload:
        if message is None or not cls._message_has_question(message):
            raise ConversationConflictError("当前会话没有等待回答的题卡。")
        question_part = message.content["parts"][0]
        try:
            return QuestionPayload.model_validate({"questions": question_part["questions"]})
        except (ValidationError, KeyError, TypeError):
            logger.warning("conversation_pending_question_invalid message_id=%s", message.id)
            raise ConversationConflictError("当前题卡状态无效，请重新发送消息。") from None

    @staticmethod
    def _message_has_question(message: Message | None) -> bool:
        if message is None or message.role != "assistant":
            return False
        parts = message.content.get("parts")
        return (
            isinstance(parts, list)
            and len(parts) == 1
            and isinstance(parts[0], dict)
            and parts[0].get("type") == "question"
        )

    @staticmethod
    def _format_answer(payload: QuestionPayload, request: QuestionAnswersRequest) -> str:
        """将已验证选项转成包含题目上下文的模型输入。"""

        answer_lines = ["用户已提交以下选择："]
        for question in payload.questions:
            answer_lines.append(f"- {question.title}：{request.answers[question.id]}")
        return "\n".join(answer_lines)

    @staticmethod
    def _validate_pagination(limit: int, offset: int) -> None:
        if limit < 1 or limit > MAX_PAGE_SIZE or offset < 0:
            raise ConversationValidationError(
                f"分页参数无效，limit 必须在 1 到 {MAX_PAGE_SIZE} 之间且 offset 不得小于 0。"
            )

    @staticmethod
    def _conversation_response(conversation: Conversation) -> ConversationCreateResponse:
        return ConversationCreateResponse(
            id=str(conversation.id),
            skill_code=conversation.skill_code,
            title=conversation.title,
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
        )

    @staticmethod
    def _message_response(message: Message) -> MessageResponse:
        return MessageResponse(
            id=str(message.id),
            conversation_id=str(message.conversation_id),
            role=message.role,
            content=MessageContent.model_validate(message.content),
            created_at=message.created_at,
        )

    def _runtime_for(self, conversation: Conversation) -> AgentRuntime | None:
        return self._agents.get(conversation.skill_code)

    @staticmethod
    def _runnable_config(
        prepared: PreparedConversationTurn,
        thread_id: str,
    ) -> dict[str, object]:
        configurable: dict[str, object] = {"thread_id": thread_id}
        if prepared.conversation.skill_code in {"image_agent", "resume_assistant"}:
            configurable.update(
                {
                    "user_id": prepared.user_id,
                    "conversation_id": prepared.conversation.id,
                    "run_id": str(prepared.message_id),
                }
            )
            if prepared.resume_answers is not None:
                configurable["resume_answers"] = prepared.resume_answers
        return {"configurable": configurable}
