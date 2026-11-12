"""定义登录保护的 JSON 会话 API；业务规则委托给 ConversationService。"""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import Response, StreamingResponse

from app.modules.auth.dependencies import validate_origin
from app.modules.conversations.dependencies.dependencies import (
    ClientIp,
    ConversationRunCoordinatorDependency,
    ConversationServiceDependency,
    CurrentUser,
)
from app.modules.conversations.schemas.schemas import (
    AgentTurnResponse,
    ConversationCreateRequest,
    ConversationCreateResponse,
    ConversationListResponse,
    ConversationRunResponse,
    MessageCreateRequest,
    MessageListResponse,
    PlaceRouteRequest,
    QuestionAnswersRequest,
)
from app.modules.digital_human.dependencies.dependencies import DigitalHumanServiceDependency
from app.modules.digital_human.service.speech_stream import stream_speech
from app.modules.membership.dependencies import require_membership_access
from app.shared.streaming import create_sse_response

router = APIRouter(prefix="/conversations", tags=["conversations"])
PageLimit = Annotated[int, Query(ge=1, le=100, description="每页条数，最大 100。")]
PageOffset = Annotated[int, Query(ge=0, description="分页偏移量。")]
IdempotencyKey = Annotated[
    str | None,
    Header(alias="Idempotency-Key", max_length=64, description="可选的单轮消息防重 UUID。"),
]


@router.post(
    "/{conversation_id}/walking-route/stream",
    dependencies=[Depends(validate_origin), Depends(require_membership_access)],
)
def stream_place_route(
    conversation_id: int,
    payload: PlaceRouteRequest,
    user: CurrentUser,
    service: ConversationServiceDependency,
) -> StreamingResponse:
    """验证会话并流式返回商家路线；业务和存储由会话服务负责。"""
    conversation = service.prepare_place_route(user, conversation_id)
    return create_sse_response(service.stream_place_route(conversation, payload))


@router.get(
    "/{conversation_id}/messages/{message_id}/static-map",
    dependencies=[Depends(require_membership_access)],
)
async def get_route_static_map(
    conversation_id: int,
    message_id: int,
    user: CurrentUser,
    service: ConversationServiceDependency,
) -> Response:
    """按需返回本人路线消息的静态地图。

    输入：会话和消息 ID 及认证用户；输出：图片字节响应；调用方：数字人路线卡片。
    """
    image, content_type = await service.get_route_static_map(
        user,
        conversation_id,
        message_id,
    )
    return Response(
        content=image,
        media_type=content_type,
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post(
    "/{conversation_id}/runs/messages",
    response_model=ConversationRunResponse,
    dependencies=[Depends(validate_origin), Depends(require_membership_access)],
)
async def start_message_run(
    conversation_id: int,
    payload: MessageCreateRequest,
    user: CurrentUser,
    service: ConversationServiceDependency,
    coordinator: ConversationRunCoordinatorDependency,
    client_ip: ClientIp,
    idempotency_key: IdempotencyKey = None,
) -> ConversationRunResponse:
    """保存用户消息并启动 Agent 任务；输入 IP 来自可信 ASGI 请求上下文。"""
    coordinator.ensure_available(user.id, conversation_id)
    prepared = service.prepare_message_stream(
        user,
        conversation_id,
        payload.message,
        idempotency_key=idempotency_key,
        client_ip=client_ip,
    )
    return ConversationRunResponse(run_id=coordinator.start(service, prepared))


@router.post(
    "/{conversation_id}/runs/answers",
    response_model=ConversationRunResponse,
    dependencies=[Depends(validate_origin), Depends(require_membership_access)],
)
async def start_answer_run(
    conversation_id: int,
    payload: QuestionAnswersRequest,
    user: CurrentUser,
    service: ConversationServiceDependency,
    coordinator: ConversationRunCoordinatorDependency,
    client_ip: ClientIp,
) -> ConversationRunResponse:
    """保存题卡答案并启动 Agent 恢复任务；IP 仅用于本轮数字人运行。"""
    coordinator.ensure_available(user.id, conversation_id)
    prepared = service.prepare_answer_stream(user, conversation_id, payload, client_ip=client_ip)
    return ConversationRunResponse(run_id=coordinator.start(service, prepared))


@router.get(
    "/{conversation_id}/runs/active",
    response_model=ConversationRunResponse | None,
    dependencies=[Depends(require_membership_access)],
)
def get_active_run(
    conversation_id: int,
    user: CurrentUser,
    coordinator: ConversationRunCoordinatorDependency,
) -> ConversationRunResponse | None:
    """查询当前用户会话中的活动任务，供页面重新进入时恢复监听。"""
    run_id = coordinator.active(user.id, conversation_id)
    return ConversationRunResponse(run_id=run_id) if run_id else None


@router.get(
    "/{conversation_id}/runs/{run_id}/listen",
    dependencies=[Depends(require_membership_access)],
)
def listen_run(
    conversation_id: int,
    run_id: str,
    user: CurrentUser,
    coordinator: ConversationRunCoordinatorDependency,
) -> StreamingResponse:
    """监听并回放任务事件；客户端断开只关闭监听。"""
    return create_sse_response(coordinator.listen(run_id, user.id, conversation_id))


@router.post(
    "/{conversation_id}/runs/{run_id}/interrupt",
    dependencies=[Depends(validate_origin), Depends(require_membership_access)],
)
def interrupt_run(
    conversation_id: int,
    run_id: str,
    user: CurrentUser,
    coordinator: ConversationRunCoordinatorDependency,
) -> dict[str, str]:
    """停止本轮 Agent 生成并保留已输出内容。"""
    coordinator.interrupt(run_id, user.id, conversation_id)
    return {"status": "interrupted"}


@router.post(
    "",
    response_model=ConversationCreateResponse,
    status_code=201,
    dependencies=[Depends(validate_origin), Depends(require_membership_access)],
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
    dependencies=[Depends(validate_origin), Depends(require_membership_access)],
)
def stream_message(
    conversation_id: int,
    payload: MessageCreateRequest,
    user: CurrentUser,
    service: ConversationServiceDependency,
    speech_service: DigitalHumanServiceDependency,
    client_ip: ClientIp,
    idempotency_key: IdempotencyKey = None,
    voice: bool = False,
) -> StreamingResponse:
    """先完成消息预检，再以 SSE 返回 Agent 回答；客户端地址仅随本轮运行传递。"""

    prepared = service.prepare_message_stream(
        user,
        conversation_id,
        payload.message,
        idempotency_key=idempotency_key,
        client_ip=client_ip,
    )
    use_voice = voice and prepared.conversation.skill_code == "digital_human"
    events = service.stream_turn(prepared, save_partial_on_cancel=use_voice)
    if use_voice:
        events = stream_speech(events, speech_service)
    return create_sse_response(events)


@router.post(
    "/{conversation_id}/messages",
    response_model=AgentTurnResponse,
    dependencies=[Depends(validate_origin), Depends(require_membership_access)],
)
def send_message(
    conversation_id: int,
    payload: MessageCreateRequest,
    user: CurrentUser,
    service: ConversationServiceDependency,
    client_ip: ClientIp,
) -> AgentTurnResponse:
    """存储用户文本并同步返回回答；客户端地址仅供本轮数字人定位使用。"""

    return service.send_message(user, conversation_id, payload.message, client_ip=client_ip)


@router.post(
    "/{conversation_id}/answers",
    response_model=AgentTurnResponse,
    dependencies=[Depends(validate_origin), Depends(require_membership_access)],
)
def answer_questions(
    conversation_id: int,
    payload: QuestionAnswersRequest,
    user: CurrentUser,
    service: ConversationServiceDependency,
    client_ip: ClientIp,
) -> AgentTurnResponse:
    """校验题卡答案并恢复 Agent；客户端地址仅用于本轮数字人定位。"""

    return service.answer_questions(user, conversation_id, payload, client_ip=client_ip)


@router.post(
    "/{conversation_id}/answers/stream",
    dependencies=[Depends(validate_origin), Depends(require_membership_access)],
)
def stream_answers(
    conversation_id: int,
    payload: QuestionAnswersRequest,
    user: CurrentUser,
    service: ConversationServiceDependency,
    speech_service: DigitalHumanServiceDependency,
    client_ip: ClientIp,
    voice: bool = False,
) -> StreamingResponse:
    """预检并保存题卡答案，再以 SSE 返回回答；IP 仅随本轮运行传递。"""

    prepared = service.prepare_answer_stream(user, conversation_id, payload, client_ip=client_ip)
    use_voice = voice and prepared.conversation.skill_code == "digital_human"
    events = service.stream_turn(prepared, save_partial_on_cancel=use_voice)
    if use_voice:
        events = stream_speech(events, speech_service)
    return create_sse_response(events)
