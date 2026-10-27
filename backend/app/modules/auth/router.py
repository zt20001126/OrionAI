from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response

from app.core.config import Settings, get_settings
from app.modules.auth.cookies import clear_session_cookie, set_session_cookie
from app.modules.auth.dependencies import get_auth_service, validate_origin
from app.modules.auth.schemas import (
    AccountResponse,
    EmailCodeRequest,
    LoginRequest,
    MessageResponse,
    PasswordResetRequest,
    RegisterRequest,
    SessionResponse,
)
from app.modules.auth.service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/email-codes",
    status_code=202,
    response_model=MessageResponse,
    dependencies=[Depends(validate_origin)],
)
def request_email_code(
    payload: EmailCodeRequest,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> MessageResponse:
    return MessageResponse(message=service.request_email_code(payload.email, payload.purpose))


@router.post(
    "/register",
    response_model=AccountResponse,
    dependencies=[Depends(validate_origin)],
)
def register(
    payload: RegisterRequest,
    response: Response,
    service: Annotated[AuthService, Depends(get_auth_service)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AccountResponse:
    account, token = service.register(payload.email, payload.code, payload.password)
    set_session_cookie(response, token, settings)
    return AccountResponse(account=account)


@router.post(
    "/login",
    response_model=AccountResponse,
    dependencies=[Depends(validate_origin)],
)
def login(
    payload: LoginRequest,
    response: Response,
    service: Annotated[AuthService, Depends(get_auth_service)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AccountResponse:
    account, token = service.login(payload.email, payload.password)
    set_session_cookie(response, token, settings)
    return AccountResponse(account=account)


@router.get("/session", response_model=SessionResponse)
def get_session(
    request: Request,
    response: Response,
    service: Annotated[AuthService, Depends(get_auth_service)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> SessionResponse:
    token = request.cookies.get(settings.auth_cookie_name)
    account = service.get_session_account(token)
    if token and account is None:
        clear_session_cookie(response, settings)
    return SessionResponse(authenticated=account is not None, account=account)


@router.post(
    "/logout",
    response_model=MessageResponse,
    dependencies=[Depends(validate_origin)],
)
def logout(
    request: Request,
    response: Response,
    service: Annotated[AuthService, Depends(get_auth_service)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> MessageResponse:
    service.logout(request.cookies.get(settings.auth_cookie_name))
    clear_session_cookie(response, settings)
    return MessageResponse(message="已退出登录。")


@router.post(
    "/password-reset",
    response_model=MessageResponse,
    dependencies=[Depends(validate_origin)],
)
def reset_password(
    payload: PasswordResetRequest,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> MessageResponse:
    service.reset_password(payload.email, payload.code, payload.new_password)
    return MessageResponse(message="密码已更新，请使用新密码登录。")
