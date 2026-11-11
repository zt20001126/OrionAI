"""编排会话权限范围、消息持久化和 BaseAgent 调用。"""

import asyncio
import hashlib
import json
import logging
import secrets
from collections.abc import AsyncIterator
from contextlib import suppress
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from functools import partial
from uuid import UUID

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
from app.core.config import get_settings
from app.infrastructure.database.session import SessionLocal
from app.infrastructure.email.email_sender import EmailDeliveryError, send_email
from app.infrastructure.redis.client import create_redis_client
from app.infrastructure.redis.conversation_run_store import ConversationRunStore
from app.infrastructure.redis.idempotency import (
    IdempotencyStore,
    IdempotencyStoreError,
    RedisIdempotencyStore,
)
from app.modules.auth.models import User
from app.modules.conversations.errors.errors import (
    ConversationConflictError,
    ConversationNotFoundError,
    ConversationUnavailableError,
    ConversationValidationError,
)
from app.modules.conversations.models.models import Conversation, Message
from app.modules.conversations.repository import repository
from app.modules.conversations.schemas.schemas import (
    AgentTurnResponse,
    ConversationCreateResponse,
    ConversationKlineChartEvent,
    ConversationListResponse,
    ConversationPlaceCardsEvent,
    ConversationQuestionEvent,
    ConversationTextDeltaEvent,
    KlineChartContentPart,
    MessageContent,
    MessageListResponse,
    MessageResponse,
    PlaceCardsContentPart,
    QuestionAnswersContentPart,
    QuestionAnswersRequest,
    QuestionContentPart,
    RouteResult,
    RouteResultContentPart,
    SubmittedQuestionAnswer,
    TextContentPart,
    UserLocationContext,
    WalkingRouteRequest,
)
from app.modules.conversations.service.title import (
    ConversationTitleGenerator,
    fallback_conversation_title,
)
from app.modules.digital_human.agent.tools.email import (
    CONFIRM_SEND,
    EMAIL_QUESTION_PREFIX,
    draft_key,
)
from app.modules.digital_human.constants import (
    DIGITAL_HUMAN_LOCATION_CONSENT_ALLOW_ANSWER,
    DIGITAL_HUMAN_LOCATION_CONSENT_QUESTION_ID,
)
from app.modules.digital_human.providers.amap.client import AmapProviderError
from app.modules.digital_human.providers.amap.walking import AmapWalkingRouteClient
from app.modules.image_generation.constants import IMAGE_RESULT_URL_PREFIX
from app.modules.skills import repository as skills_repository
from app.shared.streaming import EventType, StreamEvent

logger = logging.getLogger(__name__)
MAX_PAGE_SIZE = 100
DEFAULT_PAGE_SIZE = 50
IDEMPOTENCY_TTL_SECONDS = 24 * 60 * 60


@dataclass(frozen=True)
class PreparedConversationTurn:
    """流式响应开始前准备的一轮对话；IP 和位置数据仅保留于本轮上下文。"""

    user_id: int
    conversation: Conversation
    message_text: str
    message_id: int
    should_generate_title: bool
    client_ip: str | None = None
    location_context: UserLocationContext | None = None
    resume_answers: dict[str, str] | None = None
    idempotency_key: str | None = None
    idempotency_token: str | None = None
    cached_response_message: Message | None = None


class ConversationService:
    """实现当前用户的对话数据访问和 Agent 对话闭环。"""

    def __init__(
        self,
        *,
        session: Session,
        agent: AgentRuntime | None,
        title_generator: ConversationTitleGenerator | None = None,
        agent_registry: dict[str, AgentRuntime] | None = None,
        idempotency_store: IdempotencyStore | None = None,
    ) -> None:
        self._session = session
        self._agents = dict(agent_registry or {})
        if agent is not None:
            self._agents.setdefault(skills_repository.GENERAL_CHAT_SKILL_CODE, agent)
        self._title_generator = title_generator
        self._idempotency_store = idempotency_store

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

    def prepare_walking_route(self, user: User, conversation_id: int) -> Conversation:
        """校验路线请求的会话归属和技能；调用方：路线 API。"""
        conversation = self._get_conversation_safely(user.id, conversation_id)
        if conversation.skill_code != "digital_human":
            raise ConversationConflictError("当前会话不支持路线规划。")
        return conversation

    async def stream_walking_route(
        self, conversation: Conversation, payload: WalkingRouteRequest
    ) -> AsyncIterator[StreamEvent]:
        """转换授权位置并规划路线，保存成功结果后发送结构化事件；调用方：路线 API。"""
        client = AmapWalkingRouteClient()
        try:
            origin = await client.convert_gps(f"{payload.longitude},{payload.latitude}")
            route = await client.plan(origin, payload.destination, payload.destination_id)
            route["destination"]["name"] = payload.destination_name
            result = RouteResult.model_validate(route)
            conversation = self._get_conversation(
                conversation.user_id, conversation.id, for_update=True
            )
            message = repository.get_route_request_message(
                self._session, conversation.id, payload.request_id
            )
            if message is None:
                part = RouteResultContentPart(
                    type="route_result", data=result, request_id=payload.request_id
                )
                message = repository.create_message(
                    self._session,
                    conversation_id=conversation.id,
                    role="assistant",
                    content={"parts": [part.model_dump(mode="json")]},
                )
                repository.update_conversation_timestamp(conversation, datetime.now(UTC))
            else:
                result = RouteResultContentPart.model_validate(message.content["parts"][0]).data
            self._session.commit()
            self._session.refresh(message)
        except AmapProviderError as error:
            yield StreamEvent(
                event_type=EventType.MESSAGE, data={"type": "error", "message": str(error)}
            )
            return
        except SQLAlchemyError:
            self._session.rollback()
            yield StreamEvent(
                event_type=EventType.MESSAGE,
                data={"type": "error", "message": "保存路线失败，请重试。"},
            )
            return
        yield StreamEvent(
            event_type=EventType.MESSAGE,
            data={
                "type": "route_result",
                "data": result.model_dump(mode="json"),
                "message": self._message_response(message).model_dump(mode="json"),
            },
        )

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
            total_count = repository.count_conversations(self._session, user.id)
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
            total_count=total_count,
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
        *,
        client_ip: str | None = None,
    ) -> AgentTurnResponse:
        """保存用户文本并运行 Agent；client_ip 仅传给当前数字人运行配置。"""

        prepared = self._prepare_message_turn(
            user, conversation_id, message_text, client_ip=client_ip
        )
        if prepared.should_generate_title:
            agent_response = self._invoke_agent_and_title(
                user_id=prepared.user_id,
                conversation=prepared.conversation,
                message_text=prepared.message_text,
                message_id=prepared.message_id,
                resume_answers=prepared.resume_answers,
                client_ip=prepared.client_ip,
            )
        else:
            agent_response = self._invoke_agent(
                user_id=prepared.user_id,
                conversation_id=prepared.conversation.id,
                message_text=prepared.message_text,
                message_id=prepared.message_id,
                skill_code=prepared.conversation.skill_code,
                resume_answers=prepared.resume_answers,
                client_ip=prepared.client_ip,
                location_context=prepared.location_context,
            )
        return self._save_agent_response(prepared.conversation, agent_response)

    def answer_questions(
        self,
        user: User,
        conversation_id: int,
        request: QuestionAnswersRequest,
        *,
        client_ip: str | None = None,
    ) -> AgentTurnResponse:
        """验证题卡答案并恢复 Agent；数字人获准的位置仅作为本轮上下文传递。"""

        prepared = self._prepare_answer_turn(user, conversation_id, request, client_ip=client_ip)
        agent_response = self._invoke_agent(
            user_id=prepared.user_id,
            conversation_id=prepared.conversation.id,
            message_text=prepared.message_text,
            message_id=prepared.message_id,
            skill_code=prepared.conversation.skill_code,
            resume_answers=prepared.resume_answers,
            client_ip=prepared.client_ip,
            location_context=prepared.location_context,
        )
        return self._save_agent_response(prepared.conversation, agent_response)

    def prepare_message_stream(
        self,
        user: User,
        conversation_id: int,
        message_text: str,
        *,
        idempotency_key: str | None = None,
        client_ip: str | None = None,
    ) -> PreparedConversationTurn:
        """在 SSE 响应头发送前保存消息；client_ip 仅作为本轮内存上下文。"""

        if idempotency_key is None:
            return self._prepare_message_turn(
                user, conversation_id, message_text, client_ip=client_ip
            )
        try:
            UUID(idempotency_key)
        except ValueError:
            raise ConversationValidationError("幂等键格式无效。") from None

        conversation = self._get_conversation_safely(user.id, conversation_id)
        self._require_skill(user.id, conversation.skill_code)
        token, cached_message, retry_message = self._reserve_idempotency_key(
            user_id=user.id,
            conversation_id=conversation_id,
            idempotency_key=idempotency_key,
            message_text=message_text,
        )
        if cached_message is not None:
            return PreparedConversationTurn(
                user_id=user.id,
                conversation=conversation,
                message_text=message_text,
                message_id=cached_message.id,
                should_generate_title=False,
                client_ip=client_ip,
                idempotency_key=idempotency_key,
                cached_response_message=cached_message,
            )

        if retry_message is not None:
            return PreparedConversationTurn(
                user_id=user.id,
                conversation=conversation,
                message_text=message_text,
                message_id=retry_message.id,
                should_generate_title=False,
                client_ip=client_ip,
                idempotency_key=idempotency_key,
                idempotency_token=token,
            )

        try:
            prepared = self._prepare_message_turn(
                user, conversation_id, message_text, client_ip=client_ip
            )
        except Exception:
            self._release_idempotency_key(
                user_id=user.id,
                conversation_id=conversation_id,
                idempotency_key=idempotency_key,
                token=token,
            )
            raise
        prepared = replace(
            prepared,
            idempotency_key=idempotency_key,
            idempotency_token=token,
        )
        self._bind_idempotency_user_message(prepared)
        return prepared

    def prepare_answer_stream(
        self,
        user: User,
        conversation_id: int,
        request: QuestionAnswersRequest,
        *,
        client_ip: str | None = None,
    ) -> PreparedConversationTurn:
        """校验题卡并保存答案；client_ip 仅保留在当前 Agent 运行上下文。"""

        return self._prepare_answer_turn(user, conversation_id, request, client_ip=client_ip)

    async def stream_turn(
        self,
        prepared: PreparedConversationTurn,
        *,
        save_partial_on_cancel: bool = False,
    ) -> AsyncIterator[StreamEvent]:
        """将 Agent 文本和K线图转为 SSE 消息，并在成功或指定中断场景下保存结果。"""

        if prepared.cached_response_message is not None:
            cached_message = self._message_response(prepared.cached_response_message)
            for part in cached_message.content.parts:
                if isinstance(part, TextContentPart) and part.text:
                    yield StreamEvent(
                        event_type=EventType.MESSAGE,
                        data={"type": "text_delta", "content": part.text},
                    )
                elif isinstance(part, QuestionContentPart):
                    payload = ConversationQuestionEvent(message=cached_message)
                    yield StreamEvent(
                        event_type=EventType.MESSAGE,
                        data=payload.model_dump(mode="json"),
                    )
                elif isinstance(part, KlineChartContentPart):
                    payload = ConversationKlineChartEvent(
                        type="kline_chart",
                        content=part.content,
                    )
                    yield StreamEvent(
                        event_type=EventType.MESSAGE,
                        data=payload.model_dump(mode="json"),
                    )
                elif isinstance(part, PlaceCardsContentPart):
                    payload = ConversationPlaceCardsEvent(type="place_cards", data=part.data)
                    yield StreamEvent(
                        event_type=EventType.MESSAGE,
                        data=payload.model_dump(mode="json"),
                    )
                elif isinstance(part, RouteResultContentPart):
                    yield StreamEvent(
                        event_type=EventType.MESSAGE,
                        data={"type": "route_result", "data": part.data.model_dump(mode="json")},
                    )
            return

        agent = self._runtime_for(prepared.conversation)
        if agent is None:
            self._fail_idempotency_key(prepared)
            raise ConversationUnavailableError

        title_task = (
            asyncio.create_task(self._title_generator.generate_title(prepared.message_text))
            if prepared.should_generate_title and self._title_generator is not None
            else None
        )
        agent_response: AgentResponse | None = None
        partial_text: list[str] = []
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
                    if save_partial_on_cancel:
                        partial_text.append(event.content)
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
            self._complete_idempotency_key(
                prepared,
                assistant_message_id=int(persisted_turn.message.id),
            )
        except (asyncio.CancelledError, GeneratorExit):
            self._fail_idempotency_key(prepared)
            if title_task is not None:
                title_task.cancel()
                with suppress(asyncio.CancelledError, Exception):
                    await title_task
            with anyio.CancelScope(shield=True):
                with suppress(Exception):
                    await self._finish_stream_title(prepared, None)
                if save_partial_on_cancel and partial_text:
                    await anyio.to_thread.run_sync(
                        self._save_partial_response, prepared, "".join(partial_text)
                    )
            raise
        except Exception as error:
            self._fail_idempotency_key(prepared)
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
        elif agent_response is not None and agent_response.kline_chart is not None:
            payload = ConversationKlineChartEvent(
                type="kline_chart",
                content=agent_response.kline_chart,
            )
            yield StreamEvent(
                event_type=EventType.MESSAGE,
                data=payload.model_dump(mode="json"),
            )
        if agent_response is not None and agent_response.place_cards is not None:
            payload = ConversationPlaceCardsEvent(
                type="place_cards",
                data=agent_response.place_cards,
            )
            yield StreamEvent(
                event_type=EventType.MESSAGE,
                data=payload.model_dump(mode="json"),
            )
        if agent_response is not None and agent_response.route_result is not None:
            route = RouteResult.model_validate(agent_response.route_result)
            yield StreamEvent(
                event_type=EventType.MESSAGE,
                data={"type": "route_result", "data": route.model_dump(mode="json")},
            )

    async def execute_background_run(
        self,
        prepared: PreparedConversationTurn,
        run_store: ConversationRunStore,
        run_id: str,
    ) -> None:
        """使用独立数据库 Session 执行任务并将 SSE 事件写入 Redis。"""
        redis_client = create_redis_client()
        session = SessionLocal()
        idempotency_store = (
            RedisIdempotencyStore(redis_client) if prepared.idempotency_key else None
        )
        try:
            conversation = repository.get_conversation(
                session, prepared.user_id, prepared.conversation.id
            )
            if conversation is None:
                raise ConversationNotFoundError()
            worker = ConversationService(
                session=session,
                agent=self._agents.get(conversation.skill_code),
                agent_registry=self._agents,
                title_generator=self._title_generator,
                idempotency_store=idempotency_store,
            )
            worker_prepared = replace(prepared, conversation=conversation)
            partial_text: list[str] = []
            try:
                async for event in worker.stream_turn(worker_prepared):
                    payload = (
                        event.data
                        if isinstance(event.data, dict)
                        else event.data.model_dump(mode="json")
                    )
                    if payload.get("type") == "text_delta":
                        partial_text.append(str(payload["content"]))
                    await anyio.to_thread.run_sync(run_store.append, run_id, payload)
            except asyncio.CancelledError:
                if partial_text:
                    await anyio.to_thread.run_sync(
                        worker._save_partial_response, worker_prepared, "".join(partial_text)
                    )
                raise
        finally:
            session.close()
            redis_client.close()

    def _save_partial_response(self, prepared: PreparedConversationTurn, text: str) -> None:
        """保存用户主动中断前已生成的文本，避免刷新或离开页面后丢失。"""
        if not text.strip():
            return
        try:
            repository.create_message(
                self._session,
                conversation_id=prepared.conversation.id,
                role="assistant",
                content={"parts": [{"type": "text", "text": text}]},
            )
            conversation = repository.get_conversation(
                self._session, prepared.user_id, prepared.conversation.id
            )
            if conversation is not None:
                repository.update_conversation_timestamp(conversation, datetime.now(UTC))
            self._session.commit()
        except SQLAlchemyError:
            self._session.rollback()
            raise ConversationUnavailableError from None

    def _prepare_message_turn(
        self,
        user: User,
        conversation_id: int,
        message_text: str,
        *,
        client_ip: str | None = None,
    ) -> PreparedConversationTurn:
        """校验并保存普通消息；client_ip 仅供本轮数字人运行使用。"""

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
            client_ip=client_ip,
        )

    def _reserve_idempotency_key(
        self,
        *,
        user_id: int,
        conversation_id: int,
        idempotency_key: str,
        message_text: str,
    ) -> tuple[str, Message | None, Message | None]:
        """原子占用请求键；完成时重放，失败时重用原用户消息安全重试。"""

        if self._idempotency_store is None:
            raise ConversationUnavailableError
        redis_key = self._idempotency_key(user_id, conversation_id, idempotency_key)
        request_hash = hashlib.sha256(message_text.encode("utf-8")).hexdigest()
        token = secrets.token_urlsafe(18)
        state = {"request_hash": request_hash, "state": "processing", "token": token}
        try:
            reserved = self._idempotency_store.reserve(
                redis_key,
                json.dumps(state),
                ttl_seconds=IDEMPOTENCY_TTL_SECONDS,
            )
            if reserved:
                return token, None, None
            raw = self._idempotency_store.get(redis_key)
        except IdempotencyStoreError:
            logger.exception("conversation_idempotency_reserve_failed")
            raise ConversationUnavailableError from None

        if not raw:
            raise ConversationConflictError("本次发送状态已过期，请重新发送。")
        try:
            existing = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            raise ConversationUnavailableError from None
        if not isinstance(existing, dict):
            raise ConversationUnavailableError
        if existing.get("request_hash") != request_hash:
            raise ConversationConflictError("幂等键已用于另一条消息，请重新发送。")
        if existing.get("state") == "completed":
            message_id = existing.get("assistant_message_id")
            if not isinstance(message_id, int):
                raise ConversationUnavailableError
            try:
                message = repository.get_message_by_id(self._session, conversation_id, message_id)
            except SQLAlchemyError:
                self._session.rollback()
                raise ConversationUnavailableError from None
            if message is None or message.role != "assistant":
                raise ConversationUnavailableError
            return token, message, None
        if existing.get("state") == "failed":
            message_id = existing.get("user_message_id")
            if not isinstance(message_id, int):
                raise ConversationConflictError("本次发送未完成，请检查会话后再重新发送。")
            try:
                message = repository.get_message_by_id(self._session, conversation_id, message_id)
                has_later_messages = repository.has_messages_after(
                    self._session,
                    conversation_id,
                    message_id,
                )
            except SQLAlchemyError:
                self._session.rollback()
                raise ConversationUnavailableError from None
            if message is None or message.role != "user" or has_later_messages:
                raise ConversationConflictError("会话已继续，请不要重放较早的发送请求。")
            self._ensure_not_waiting(conversation_id)
            retry_token = secrets.token_urlsafe(18)
            retry_state = {
                "request_hash": request_hash,
                "state": "processing",
                "token": retry_token,
                "user_message_id": message.id,
            }
            try:
                reserved_retry = self._idempotency_store.set_if_state(
                    redis_key,
                    "failed",
                    request_hash,
                    json.dumps(retry_state),
                    ttl_seconds=IDEMPOTENCY_TTL_SECONDS,
                )
            except IdempotencyStoreError:
                logger.exception("conversation_idempotency_retry_reserve_failed")
                raise ConversationUnavailableError from None
            if not reserved_retry:
                raise ConversationConflictError("相同消息正在重试，请稍候。")
            return retry_token, None, message
        raise ConversationConflictError("相同消息仍在处理中，请稍候。")

    def _bind_idempotency_user_message(self, prepared: PreparedConversationTurn) -> None:
        """保存已创建的用户消息 ID，使失败后的同键重试复用原消息。"""

        if not prepared.idempotency_key or not prepared.idempotency_token:
            return
        redis_key = self._idempotency_key(
            prepared.user_id,
            prepared.conversation.id,
            prepared.idempotency_key,
        )
        value = json.dumps(
            {
                "request_hash": hashlib.sha256(prepared.message_text.encode("utf-8")).hexdigest(),
                "state": "processing",
                "token": prepared.idempotency_token,
                "user_message_id": prepared.message_id,
            }
        )
        try:
            saved = self._idempotency_store.set_if_token(
                redis_key,
                prepared.idempotency_token,
                value,
                ttl_seconds=IDEMPOTENCY_TTL_SECONDS,
            )
        except IdempotencyStoreError:
            logger.exception("conversation_idempotency_user_message_bind_failed")
            raise ConversationUnavailableError from None
        if not saved:
            raise ConversationConflictError("本次发送状态已过期，请重新发送。")

    def _complete_idempotency_key(
        self,
        prepared: PreparedConversationTurn,
        assistant_message_id: int,
    ) -> None:
        """在助手消息提交后记录重放指针；Redis 故障不影响已提交的回复。"""

        if not prepared.idempotency_key or not prepared.idempotency_token:
            return
        redis_key = self._idempotency_key(
            prepared.user_id,
            prepared.conversation.id,
            prepared.idempotency_key,
        )
        value = json.dumps(
            {
                "request_hash": hashlib.sha256(prepared.message_text.encode("utf-8")).hexdigest(),
                "state": "completed",
                "assistant_message_id": assistant_message_id,
            }
        )
        try:
            self._idempotency_store.set_if_token(
                redis_key,
                prepared.idempotency_token,
                value,
                ttl_seconds=IDEMPOTENCY_TTL_SECONDS,
            )
        except IdempotencyStoreError:
            logger.exception("conversation_idempotency_complete_failed")

    def _fail_idempotency_key(self, prepared: PreparedConversationTurn) -> None:
        """记录失败轮次和原用户消息 ID，供同键重试复用。"""

        if not prepared.idempotency_key or not prepared.idempotency_token:
            return
        redis_key = self._idempotency_key(
            prepared.user_id,
            prepared.conversation.id,
            prepared.idempotency_key,
        )
        value = json.dumps(
            {
                "request_hash": hashlib.sha256(prepared.message_text.encode("utf-8")).hexdigest(),
                "state": "failed",
                "user_message_id": prepared.message_id,
            }
        )
        try:
            self._idempotency_store.set_if_token(
                redis_key,
                prepared.idempotency_token,
                value,
                ttl_seconds=IDEMPOTENCY_TTL_SECONDS,
            )
        except IdempotencyStoreError:
            logger.exception("conversation_idempotency_fail_update_failed")

    def _release_idempotency_key(
        self,
        *,
        user_id: int,
        conversation_id: int,
        idempotency_key: str,
        token: str,
    ) -> None:
        """请求预检失败时释放本次预留，允许用户纠正后重试。"""

        if self._idempotency_store is None:
            return
        redis_key = self._idempotency_key(user_id, conversation_id, idempotency_key)
        try:
            self._idempotency_store.delete_if_token(redis_key, token)
        except (IdempotencyStoreError, TypeError, json.JSONDecodeError):
            logger.exception("conversation_idempotency_release_failed")

    @staticmethod
    def _idempotency_key(user_id: int, conversation_id: int, key: str) -> str:
        return f"orionai:conversation:turn:{user_id}:{conversation_id}:{key}"

    def _prepare_answer_turn(
        self,
        user: User,
        conversation_id: int,
        request: QuestionAnswersRequest,
        *,
        client_ip: str | None = None,
    ) -> PreparedConversationTurn:
        """校验并保存题卡答案。

        输入：当前用户、会话 ID、题卡答案及可选的浏览器位置；输出：恢复 Agent 所需的本轮数据；
        调用方：同步答题接口和后台问答任务。授权坐标只留在数字人本轮上下文，不写入消息。
        """

        conversation = self._get_conversation_safely(user.id, conversation_id)
        self._require_skill(user.id, conversation.skill_code)
        latest_message = self._get_latest_message_safely(conversation.id)
        question_payload = self._pending_questions(latest_message)
        try:
            question_payload.validate_answers(request.answers)
        except ValueError as error:
            raise ConversationValidationError(str(error)) from None

        if request.location is not None:
            location_question = next(
                (
                    question
                    for question in question_payload.questions
                    if question.id == DIGITAL_HUMAN_LOCATION_CONSENT_QUESTION_ID
                ),
                None,
            )
            if (
                conversation.skill_code != "digital_human"
                or location_question is None
                or request.answers.get(DIGITAL_HUMAN_LOCATION_CONSENT_QUESTION_ID)
                != DIGITAL_HUMAN_LOCATION_CONSENT_ALLOW_ANSWER
            ):
                raise ConversationValidationError("只有数字人位置授权题卡允许提交定位结果。")

        answer_text = self._format_answer(question_payload, request)
        if conversation.skill_code == "digital_human" and len(question_payload.questions) == 1:
            question = question_payload.questions[0]
            if question.id.startswith(EMAIL_QUESTION_PREFIX):
                answer_text += "\n" + self._process_email_confirmation(
                    user.id, conversation.id, question, request.answers[question.id]
                )
        question_answers = QuestionAnswersContentPart(
            type="question_answers",
            items=[
                SubmittedQuestionAnswer(
                    question_id=question.id,
                    question=question.title,
                    answer=request.answers[question.id],
                )
                for question in question_payload.questions
            ],
        )
        user_message = self._save_user_message(
            conversation,
            answer_text,
            question_answers=question_answers,
        )
        return PreparedConversationTurn(
            user_id=user.id,
            conversation=conversation,
            message_text=answer_text,
            message_id=user_message.id,
            should_generate_title=False,
            client_ip=client_ip,
            resume_answers=request.answers,
            location_context=request.location,
        )

    @staticmethod
    def _process_email_confirmation(
        user_id: int, conversation_id: int, question: object, answer: str
    ) -> str:
        """原子领取已确认草稿并发送；输入题卡和用户选择，输出明确的发送结果。"""
        from app.agent.schemas import Question

        if not isinstance(question, Question):
            raise ConversationValidationError("邮件确认题卡无效。")
        client = create_redis_client()
        try:
            key = draft_key(user_id, conversation_id, question.id)
            # 先对比用户实际看到的内容，再原子领取，避免并发重复发送。
            raw = client.get(key)
            if raw is None:
                return "邮件草稿已失效或已处理，请重新准备邮件。"
            saved = json.loads(raw)
            if (
                saved["preview"] != question.context
                or saved["sender"] != get_settings().smtp_from_email
            ):
                raise ConversationValidationError("邮件确认内容不匹配，请重新准备邮件。")
            claimed = client.getdel(key)
            if claimed is None:
                return "邮件草稿已处理，请勿重复发送。"
        finally:
            client.close()
        if answer != CONFIRM_SEND:
            return "用户取消了邮件发送，邮件未发送。"
        draft = json.loads(claimed)["draft"]
        try:
            send_email(
                get_settings(),
                recipient=draft["recipient"],
                subject=draft["subject"],
                text_body=draft["body"],
            )
        except EmailDeliveryError:
            return "邮件发送未确认成功；请告知用户结果可能不确定，不要自动重试。"
        return "SMTP 服务器已接受邮件；这不表示邮件已送达。"

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
        client_ip: str | None = None,
        location_context: UserLocationContext | None = None,
    ) -> AgentResponse:
        """调度技能 Runtime。

        输入：用户/会话标识、消息、技能和可选本轮上下文；输出：Agent 回答。
        调用方：同步对话与答题 Service。
        数字人 IP 和授权位置只进入当前运行配置，Agent 异常在此转换为会话业务错误。
        """

        agent = self._agents.get(skill_code)
        if agent is None:
            raise ConversationUnavailableError
        thread_id = build_conversation_thread_id(user_id, conversation_id, skill_code)
        configurable: dict[str, object] = {"thread_id": thread_id}
        if skill_code in {"image_agent", "resume_assistant", "tourism_insight", "digital_human"}:
            configurable.update(
                {
                    "user_id": user_id,
                    "conversation_id": conversation_id,
                    "run_id": str(message_id),
                }
            )
            if resume_answers is not None:
                configurable["resume_answers"] = resume_answers
        if skill_code == "digital_human" and client_ip is not None:
            configurable["client_ip"] = client_ip
        if skill_code == "digital_human" and location_context is not None:
            configurable["user_location"] = location_context.model_dump(exclude_none=True)
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
        client_ip: str | None = None,
    ) -> AgentResponse:
        """并行生成首轮标题与 Agent；client_ip 仅传给本轮数字人运行。"""

        agent = self._runtime_for(conversation)
        if agent is None:
            raise ConversationUnavailableError
        thread_id = build_conversation_thread_id(user_id, conversation.id, conversation.skill_code)
        request = AgentRequest(message=message_text)
        configurable: dict[str, object] = {
            "thread_id": thread_id,
        }
        if conversation.skill_code in {
            "image_agent",
            "resume_assistant",
            "tourism_insight",
            "digital_human",
        }:
            configurable.update(
                {
                    "user_id": user_id,
                    "conversation_id": conversation.id,
                    "run_id": str(message_id),
                }
            )
            if resume_answers is not None:
                configurable["resume_answers"] = resume_answers
        if conversation.skill_code == "digital_human" and client_ip is not None:
            configurable["client_ip"] = client_ip
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
            if response.video_result_id is not None:
                parts.append(
                    {
                        "type": "video_result",
                        "task_result_id": response.video_result_id,
                        "generation_status": "succeeded",
                        "video_url": (
                            f"/api/digital-human/task-results/{response.video_result_id}/video"
                        ),
                    }
                )
            if response.kline_chart is not None:
                parts.append(
                    KlineChartContentPart(
                        type="kline_chart",
                        content=response.kline_chart,
                    ).model_dump(mode="json")
                )
            if response.place_cards is not None:
                parts.append(
                    PlaceCardsContentPart(
                        type="place_cards",
                        data=response.place_cards,
                    ).model_dump(mode="json")
                )
            if response.route_result is not None:
                parts.append(
                    RouteResultContentPart(
                        type="route_result", data=RouteResult.model_validate(response.route_result)
                    ).model_dump(mode="json")
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
        *,
        question_answers: QuestionAnswersContentPart | None = None,
    ) -> Message:
        """先提交用户消息和可选题目答案，使其 ID 可作为 LangGraph 消息稳定标识。"""

        try:
            content_parts: list[dict[str, object]] = [{"type": "text", "text": message_text}]
            if question_answers is not None:
                content_parts.append(question_answers.model_dump(mode="json"))
            user_message = repository.create_message(
                self._session,
                conversation_id=conversation.id,
                role="user",
                content={"parts": content_parts},
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
        """构造单轮 Agent 配置；输入已准备的会话轮次和线程 ID，输出 Runtime 配置。

        调用方：后台流式执行。
        """
        configurable: dict[str, object] = {"thread_id": thread_id}
        if prepared.conversation.skill_code in {
            "image_agent",
            "resume_assistant",
            "tourism_insight",
            "digital_human",
        }:
            configurable.update(
                {
                    "user_id": prepared.user_id,
                    "conversation_id": prepared.conversation.id,
                    "run_id": str(prepared.message_id),
                }
            )
            if prepared.resume_answers is not None:
                configurable["resume_answers"] = prepared.resume_answers
        if prepared.conversation.skill_code == "digital_human" and prepared.client_ip is not None:
            configurable["client_ip"] = prepared.client_ip
        if (
            prepared.conversation.skill_code == "digital_human"
            and prepared.location_context is not None
        ):
            configurable["user_location"] = prepared.location_context.model_dump(exclude_none=True)
        return {"configurable": configurable}
