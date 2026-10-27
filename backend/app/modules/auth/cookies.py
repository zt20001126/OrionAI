"""提供认证 Cookie 的统一设置和清理逻辑。"""

from fastapi import Response

from app.core.config import Settings


def _cookie_is_secure(settings: Settings) -> bool:
    if settings.auth_cookie_secure is not None:
        return settings.auth_cookie_secure
    return settings.environment.lower() in {"prod", "production"}


def set_session_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        key=settings.auth_cookie_name,
        value=token,
        max_age=settings.auth_session_ttl_seconds,
        httponly=True,
        secure=_cookie_is_secure(settings),
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        key=settings.auth_cookie_name,
        httponly=True,
        secure=_cookie_is_secure(settings),
        samesite="lax",
        path="/",
    )
