"""定义登录保护的 JSON 会话 API；业务规则委托给 ConversationService。"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from app.modules.auth.dependencies import validate_origin
from app.modules.conversations.dependencies import ConversationServiceDependency, CurrentUser
from app.modules.conversations.schemas import (
    AgentTurnResponse,
    ConversationCreateRequest,
    ConversationCreateResponse,
    ConversationListResponse,
    MessageCreateRequest,
    MessageListResponse,
    QuestionAnswersRequest,
)
from app.shared.streaming import create_sse_response

router = APIRouter(prefix="/conversations", tags=["conversations"])
PageLimit = Annotated[int, Query(ge=1, le=100, description="每页条数，最大 100。")]
PageOffset = Annotated[int, Query(ge=0, description="分页偏移量。")]


@router.post(
    "",
    response_model=ConversationCreateResponse,
    status_code=201,
    dependencies=[Depends(validate_origin)],
)
def create_conversation(
    user: CurrentUser,
    service: ConversationServiceDependency,
    payload: ConversationCreateRequest | None = None,
) -> ConversationCreateResponse:
    """为当前用户创建空会话。"""

    return service.create_conversation(
        user, skill_code=payload.skill_code if payload else "general_chat"
    )


@router.get("", response_model=ConversationListResponse)
def list_conversations(
    user: CurrentUser,
    service: ConversationServiceDependency,
    limit: PageLimit = 50,
    offset: PageOffset = 0,
) -> ConversationListResponse:
    """按最近更新时间倒序列出当前用户会话。"""

    return service.list_conversations(user, limit=limit, offset=offset)


@router.get("/{conversation_id}/messages", response_model=MessageListResponse)
def list_messages(
    conversation_id: int,
    user: CurrentUser,
    service: ConversationServiceDependency,
    limit: PageLimit = 50,
    offset: PageOffset = 0,
) -> MessageListResponse:
    """读取当前用户会话中的消息记录。"""

    return service.list_messages(user, conversation_id, limit=limit, offset=offset)


@router.post(
    "/{conversation_id}/messages/stream",
    dependencies=[Depends(validate_origin)],
)
def stream_message(
    conversation_id: int,
    payload: MessageCreateRequest,
    user: CurrentUser,
    service: ConversationServiceDependency,
) -> StreamingResponse:
    """先完成消息预检，再以 SSE 返回 Agent 的逐段回答。"""

    prepared = service.prepare_message_stream(user, conversation_id, payload.message)
    return create_sse_response(service.stream_turn(prepared))


@router.post(
    "/{conversation_id}/messages",
    response_model=AgentTurnResponse,
    dependencies=[Depends(validate_origin)],
)
def send_message(
    conversation_id: int,
    payload: MessageCreateRequest,
    user: CurrentUser,
    service: ConversationServiceDependency,
) -> AgentTurnResponse:
    """存储用户文本并同步返回助手回答或题卡。"""

    return service.send_message(user, conversation_id, payload.message)


@router.post(
    "/{conversation_id}/answers",
    response_model=AgentTurnResponse,
    dependencies=[Depends(validate_origin)],
)
def answer_questions(
    conversation_id: int,
    payload: QuestionAnswersRequest,
    user: CurrentUser,
    service: ConversationServiceDependency,
) -> AgentTurnResponse:
    """校验当前待答题卡选项并恢复原对话线程。"""

    return service.answer_questions(user, conversation_id, payload)


@router.post(
    "/{conversation_id}/answers/stream",
    dependencies=[Depends(validate_origin)],
)
def stream_answers(
    conversation_id: int,
    payload: QuestionAnswersRequest,
    user: CurrentUser,
    service: ConversationServiceDependency,
) -> StreamingResponse:
    """预检并保存题卡答案，再以 SSE 返回恢复后的 Agent 回答。"""

    prepared = service.prepare_answer_stream(user, conversation_id, payload)
    return create_sse_response(service.stream_turn(prepared))
