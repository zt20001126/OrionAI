"""提供 conversations Router 所需的认证、数据库与 Agent 依赖。"""

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.agent.runtime.base_agent import BaseAgent
from app.infrastructure.database.session import get_db_session
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.conversations.service import ConversationService


def get_conversation_service(
    session: Annotated[Session, Depends(get_db_session)],
    request: Request,
) -> ConversationService:
    """从应用组合根取 Agent，并构造每请求的对话 Service。"""

    agent: BaseAgent | None = getattr(request.app.state, "conversation_agent", None)
    return ConversationService(session=session, agent=agent)


CurrentUser = Annotated[User, Depends(get_current_user)]
ConversationServiceDependency = Annotated[
    ConversationService,
    Depends(get_conversation_service),
]
