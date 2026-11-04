"""构造文旅洞察请求范围的 Service 并复用认证依赖。"""

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.infrastructure.database.session import get_db_session
from app.modules.auth.dependencies import CurrentUser
from app.modules.tourism_insight.service.service import TourismInsightService

__all__ = ["CurrentUser", "TourismInsightServiceDependency", "get_tourism_insight_service"]


def get_tourism_insight_service(
    session: Annotated[Session, Depends(get_db_session)],
    request: Request,
) -> TourismInsightService:
    """注入本请求数据库会话及应用生命周期内的 Agent Runtime。"""
    return TourismInsightService(session, getattr(request.app.state, "tourism_insight_agent", None))


TourismInsightServiceDependency = Annotated[
    TourismInsightService, Depends(get_tourism_insight_service)
]
