"""定义当前登录用户的资料读取和保存 API。"""

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile

from app.core.config import Settings, get_settings
from app.modules.auth.cookies import clear_session_cookie
from app.modules.auth.dependencies import get_auth_service, validate_origin
from app.modules.auth.schemas import MessageResponse, PasswordChangeRequest
from app.modules.auth.service import AuthService
from app.modules.users.constants import MAX_AVATAR_UPLOAD_BYTES
from app.modules.users.dependencies import CurrentUser, UsersServiceDependency
from app.modules.users.schemas import UpdateUserProfileRequest, UserProfileResponse

router = APIRouter(prefix="/v1/users", tags=["users"])


@router.get("/me", response_model=UserProfileResponse)
def get_my_profile(
    user: CurrentUser,
    service: UsersServiceDependency,
) -> UserProfileResponse:
    """读取当前登录用户资料。"""

    return service.get_profile(user)


@router.patch(
    "/me",
    response_model=UserProfileResponse,
    dependencies=[Depends(validate_origin)],
)
def update_my_profile(
    payload: Annotated[UpdateUserProfileRequest, Form()],
    user: CurrentUser,
    service: UsersServiceDependency,
    avatar: Annotated[
        UploadFile | None,
        File(description="可选头像图片，支持 PNG、JPEG 或 WebP，最大 2 MiB"),
    ] = None,
) -> UserProfileResponse:
    """一次提交当前用户昵称和可选头像文件。"""

    avatar_data = None if avatar is None else avatar.file.read(MAX_AVATAR_UPLOAD_BYTES + 1)
    avatar_content_type = None if avatar is None else avatar.content_type
    return service.update_profile(
        user,
        payload,
        avatar_data=avatar_data,
        avatar_content_type=avatar_content_type,
    )


@router.post(
    "/me/password/code",
    status_code=202,
    response_model=MessageResponse,
    dependencies=[Depends(validate_origin)],
)
def send_password_change_code(
    user: CurrentUser,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> MessageResponse:
    """向当前登录用户绑定的邮箱发送修改密码验证码。"""

    return MessageResponse(message=service.request_password_change_code(user.account))


@router.put(
    "/me/password",
    response_model=MessageResponse,
    dependencies=[Depends(validate_origin)],
)
def change_my_password(
    payload: PasswordChangeRequest,
    response: Response,
    user: CurrentUser,
    service: Annotated[AuthService, Depends(get_auth_service)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> MessageResponse:
    """修改当前用户密码并清除当前浏览器会话 Cookie。"""

    service.change_password(user.account, payload.code, payload.new_password)
    clear_session_cookie(response, settings)
    return MessageResponse(message="密码已修改，请使用新密码重新登录。")
