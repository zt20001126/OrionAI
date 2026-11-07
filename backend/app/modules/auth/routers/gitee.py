"""定义 Gitee 登录、账号绑定和统一 OAuth 回调路由。"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import RedirectResponse
from redis import Redis
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.infrastructure.database.session import get_db_session
from app.infrastructure.redis.auth_state import RedisAuthStateStore
from app.infrastructure.redis.client import get_redis_client
from app.modules.auth.cookies import set_session_cookie
from app.modules.auth.dependencies import RegisteredUser, get_auth_service
from app.modules.auth.errors import OAuthAccountConflictError, OAuthEmailConflictError, OAuthError
from app.modules.auth.services.auth import AuthService
from app.modules.auth.services.gitee import GiteeOAuthService

router = APIRouter(tags=["auth"])


def get_gitee_oauth_service(
    session: Annotated[Session, Depends(get_db_session)],
    redis_client: Annotated[Redis, Depends(get_redis_client)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> GiteeOAuthService:
    """构造 Gitee OAuth Service；输入：数据库、Redis 和配置；输出：Service；调用方：本路由。"""
    return GiteeOAuthService(session, RedisAuthStateStore(redis_client), settings)


@router.get("/gitee/login")
def gitee_login(
    service: Annotated[GiteeOAuthService, Depends(get_gitee_oauth_service)],
) -> RedirectResponse:
    """发起 Gitee 登录；输入：OAuth Service；输出：授权重定向；调用方：登录页。"""
    return RedirectResponse(service.authorization_url(), status_code=302)


@router.get("/gitee/bind")
def gitee_bind(
    user: RegisteredUser,
    service: Annotated[GiteeOAuthService, Depends(get_gitee_oauth_service)],
) -> RedirectResponse:
    """为当前注册用户发起 Gitee 绑定。

    输入：当前用户和 OAuth Service；输出：授权重定向；调用方：安全设置页。
    """
    return RedirectResponse(service.authorization_url(user), status_code=302)


@router.get("/gitee/callback")
def gitee_callback(
    request: Request,
    service: Annotated[GiteeOAuthService, Depends(get_gitee_oauth_service)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
    settings: Annotated[Settings, Depends(get_settings)],
    code: Annotated[str | None, Query()] = None,
    state: Annotated[str | None, Query()] = None,
    error: Annotated[str | None, Query()] = None,
) -> RedirectResponse:
    """处理 Gitee 登录或绑定回调。

    输入：授权参数和 Cookie；输出：前端重定向与登录 Cookie；调用方：Gitee OAuth。
    """
    frontend_url = settings.auth_frontend_base_url.rstrip("/")
    current_user = auth_service.get_session_user(request.cookies.get(settings.auth_cookie_name))
    if error:
        service.discard_state(state)
        return RedirectResponse(f"{frontend_url}/?oauth_error=denied", status_code=302)
    try:
        session_token = service.callback(code, state, current_user)
    except OAuthEmailConflictError:
        return RedirectResponse(f"{frontend_url}/?oauth_error=email_conflict", status_code=302)
    except OAuthAccountConflictError:
        return RedirectResponse(f"{frontend_url}/?oauth_error=account_conflict", status_code=302)
    except OAuthError:
        return RedirectResponse(f"{frontend_url}/?oauth_error=invalid", status_code=302)
    if session_token:
        redirect = RedirectResponse(f"{frontend_url}/digital-human", status_code=302)
        set_session_cookie(redirect, session_token, settings)
        return redirect
    return RedirectResponse(f"{frontend_url}/settings?oauth_success=gitee_bound", status_code=302)
