"""提供认证模块共享依赖，将有效 Cookie Session 映射为当前用户。"""

from typing import Annotated
from urllib.parse import urlsplit

from fastapi import Depends, HTTPException, Request
from redis import Redis
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.infrastructure.database.session import get_db_session
from app.infrastructure.redis.auth_state import RedisAuthStateStore
from app.infrastructure.redis.client import get_redis_client
from app.modules.auth.errors import AuthUnavailableError
from app.modules.auth.models import User
from app.modules.auth.repository import get_user
from app.modules.auth.service import AuthService


def get_auth_service(
    session: Annotated[Session, Depends(get_db_session)],
    redis_client: Annotated[Redis, Depends(get_redis_client)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthService:
    """构造认证 Service，供认证路由和当前用户依赖复用。"""

    return AuthService(session, RedisAuthStateStore(redis_client), settings)


def get_current_user(
    request: Request,
    session: Annotated[Session, Depends(get_db_session)],
    redis_client: Annotated[Redis, Depends(get_redis_client)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> User:
    """验证 Cookie Session 并返回用户 ORM，拒绝匿名访问会话数据。"""

    auth_service = AuthService(session, RedisAuthStateStore(redis_client), settings)
    account = auth_service.get_session_account(request.cookies.get(settings.auth_cookie_name))
    if account is None:
        raise HTTPException(status_code=401, detail="请先登录。")

    try:
        user = get_user(session, account)
    except SQLAlchemyError:
        session.rollback()
        raise AuthUnavailableError from None
    if user is None:
        raise HTTPException(status_code=401, detail="登录状态已失效，请重新登录。")
    return user


def validate_origin(request: Request) -> None:
    """校验带 Cookie 的状态变更请求来源，沿用认证接口的同源约束。"""

    origin = request.headers.get("origin")
    if not origin:
        return
    parsed_origin = urlsplit(origin)
    request_host = request.headers.get("host", "")
    if (
        parsed_origin.scheme not in {"http", "https"}
        or not parsed_origin.netloc
        or parsed_origin.netloc.lower() != request_host.lower()
    ):
        raise HTTPException(status_code=403, detail="请求来源无效。")
