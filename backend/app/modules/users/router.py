"""定义当前登录用户的资料读取和保存 API。"""

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile

from app.modules.auth.dependencies import validate_origin
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
        File(description="可选头像图片，支持 PNG、JPEG 或 WebP，最大 5 MiB"),
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
