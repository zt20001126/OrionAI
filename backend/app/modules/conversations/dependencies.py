"""提供 conversations Router 所需的认证、数据库与 Agent 依赖。"""

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.agent.runtime.protocol import AgentRuntime
from app.infrastructure.database.session import get_db_session
from app.infrastructure.redis.client import create_redis_client
from app.infrastructure.redis.idempotency import IdempotencyStore, RedisIdempotencyStore
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.conversations.run_coordinator import ConversationRunCoordinator
from app.modules.conversations.service import ConversationService
from app.modules.conversations.title import ConversationTitleGenerator


def get_optional_idempotency_store(request: Request) -> Iterator[IdempotencyStore | None]:
    """仅为显式带幂等键的流式请求创建 Redis 幂等存储适配器。"""

    if not request.headers.get("idempotency-key"):
        yield None
        return
    redis_client = create_redis_client()
    try:
        yield RedisIdempotencyStore(redis_client)
    finally:
        redis_client.close()


def get_conversation_service(
    session: Annotated[Session, Depends(get_db_session)],
    request: Request,
    idempotency_store: Annotated[
        IdempotencyStore | None,
        Depends(get_optional_idempotency_store),
    ],
) -> ConversationService:
    """从应用组合根取 Agent，并构造每请求的对话 Service。"""

    agent_registry = dict(getattr(request.app.state, "agent_registry", {}))
    agent: AgentRuntime | None = getattr(request.app.state, "conversation_agent", None)
    title_generator: ConversationTitleGenerator | None = getattr(
        request.app.state,
        "conversation_title_generator",
        None,
    )
    return ConversationService(
        session=session,
        agent=agent,
        agent_registry=agent_registry,
        title_generator=title_generator,
        idempotency_store=idempotency_store,
    )


async def get_conversation_run_coordinator(request: Request) -> ConversationRunCoordinator:
    """为应用复用 Redis 任务协调器，确保同一进程内可取消正在执行的协程。"""
    coordinator = getattr(request.app.state, "conversation_run_coordinator", None)
    if coordinator is None:
        coordinator = ConversationRunCoordinator(create_redis_client())
        request.app.state.conversation_run_coordinator = coordinator
    return coordinator


CurrentUser = Annotated[User, Depends(get_current_user)]
ConversationServiceDependency = Annotated[
    ConversationService,
    Depends(get_conversation_service),
]
ConversationRunCoordinatorDependency = Annotated[
    ConversationRunCoordinator,
    Depends(get_conversation_run_coordinator),
]
