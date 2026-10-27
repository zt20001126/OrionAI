"""协调用户个人资料校验、数据库更新与 OSS 头像对象生命周期。"""

import logging
from collections.abc import Callable
from typing import Protocol
from uuid import uuid4

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.infrastructure.storage.aliyun_oss import AliyunOSSObjectStorage
from app.infrastructure.storage.object_storage import ObjectMetadata, ObjectStorageError
from app.modules.auth.models import DEFAULT_USER_AVATAR_URL, User
from app.modules.users import repository
from app.modules.users.constants import (
    JPEG_SIGNATURE,
    MAX_AVATAR_UPLOAD_BYTES,
    MAX_NICKNAME_LENGTH,
    PNG_SIGNATURE,
    WEBP_FORMAT_SIGNATURE,
    WEBP_RIFF_SIGNATURE,
)
from app.modules.users.errors import (
    InvalidUserProfileError,
    UserProfileNotFoundError,
    UsersUnavailableError,
)
from app.modules.users.schemas import UpdateUserProfileRequest, UserProfileResponse

logger = logging.getLogger(__name__)


class AvatarStorage(Protocol):
    """用户头像业务使用的 OSS 对象操作边界。"""

    def put_object(
        self,
        key: str,
        data: bytes,
        *,
        content_type: str,
        public_read: bool = False,
    ) -> ObjectMetadata: ...

    def build_public_url(self, key: str) -> str: ...

    def key_from_public_url(self, public_url: str) -> str | None: ...

    def delete_object(self, key: str) -> None: ...


class UsersService:
    """编排当前用户资料查询、保存和公开头像对象维护。"""

    def __init__(
        self,
        *,
        session: Session,
        settings: Settings,
        storage_factory: Callable[[], AvatarStorage] | None = None,
    ) -> None:
        self._session = session
        self._settings = settings
        self._storage_factory = storage_factory or (lambda: AliyunOSSObjectStorage(self._settings))

    def get_profile(self, current_user: User) -> UserProfileResponse:
        """读取当前用户个人资料。

        Step 1: 通过认证依赖提供的用户 ID 从 Repository 读取最新资料。
        Step 2: 将空昵称回退为邮箱本地部分并构造响应 DTO。
        """

        try:
            user = repository.get_user_by_id(self._session, current_user.id)
        except SQLAlchemyError:
            self._session.rollback()
            raise UsersUnavailableError from None
        if user is None:
            raise UserProfileNotFoundError
        return self._profile_response(user)

    def update_profile(
        self,
        current_user: User,
        payload: UpdateUserProfileRequest,
        *,
        avatar_data: bytes | None,
        avatar_content_type: str | None,
    ) -> UserProfileResponse:
        """保存当前用户的昵称及可选头像。

        Step 1: 规范化昵称并验证头像实际格式和大小。
        Step 2: 如有新头像，先以对象级公共读上传唯一 OSS 对象。
        Step 3: 在同一数据库提交中保存昵称和新对象键；提交失败时补偿删除新对象。
        Step 4: 提交成功后尽力清理旧 OSS 头像并返回最新资料。
        """

        nickname = payload.nickname.strip()
        if not nickname or len(nickname) > MAX_NICKNAME_LENGTH:
            raise InvalidUserProfileError("昵称不能为空，且不能超过 20 个字符。")

        try:
            existing_user = repository.get_user_by_id(self._session, current_user.id)
        except SQLAlchemyError:
            self._session.rollback()
            raise UsersUnavailableError from None
        if existing_user is None:
            raise UserProfileNotFoundError

        uploaded_key: str | None = None
        storage: AvatarStorage | None = None
        old_avatar_key = existing_user.avatar_key
        old_avatar_url = existing_user.avatar_url
        if avatar_data is not None:
            if avatar_content_type is None:
                raise InvalidUserProfileError("头像文件类型无效，请选择 PNG、JPEG 或 WebP 图片。")
            mime_type, extension = _validate_avatar(avatar_data, avatar_content_type)
            uploaded_key = f"users/{current_user.id}/avatars/{uuid4().hex}.{extension}"
            try:
                storage = self._storage_factory()
                storage.put_object(
                    uploaded_key,
                    avatar_data,
                    content_type=mime_type,
                    public_read=True,
                )
            except (ObjectStorageError, ValueError):
                if storage is not None:
                    self._delete_uploaded_object(storage, uploaded_key, current_user.id)
                raise UsersUnavailableError from None

        try:
            user = repository.update_user_profile(
                self._session,
                current_user.id,
                nickname=nickname,
                avatar_key=uploaded_key,
            )
        except SQLAlchemyError:
            self._session.rollback()
            if storage is not None and uploaded_key is not None:
                self._delete_uploaded_object(storage, uploaded_key, current_user.id)
            raise UsersUnavailableError from None
        if user is None:
            if storage is not None and uploaded_key is not None:
                self._delete_uploaded_object(storage, uploaded_key, current_user.id)
            raise UserProfileNotFoundError

        if storage is not None and uploaded_key is not None:
            old_key = old_avatar_key
            if old_key is None and old_avatar_url and old_avatar_url != DEFAULT_USER_AVATAR_URL:
                old_key = storage.key_from_public_url(old_avatar_url)
            if (
                old_key is not None
                and old_key.startswith(f"users/{current_user.id}/avatars/")
                and old_key != uploaded_key
            ):
                self._delete_replaced_object(storage, old_key, current_user.id)
        return self._profile_response(user)

    def _profile_response(self, user: User) -> UserProfileResponse:
        nickname = (user.nickname or "").strip()
        if not nickname:
            nickname = user.account.partition("@")[0][:MAX_NICKNAME_LENGTH] or "个人用户"
        avatar_url = user.avatar_url
        if user.avatar_key:
            if not user.avatar_key.startswith(f"users/{user.id}/avatars/"):
                raise UsersUnavailableError
            try:
                avatar_url = self._storage_factory().build_public_url(user.avatar_key)
            except (ObjectStorageError, ValueError):
                raise UsersUnavailableError from None
        if not avatar_url or avatar_url == DEFAULT_USER_AVATAR_URL:
            avatar_url = DEFAULT_USER_AVATAR_URL
        return UserProfileResponse(
            nickname=nickname,
            account=user.account,
            avatar_url=avatar_url,
            created_at=user.created_at,
            last_login_at=user.last_login_at,
        )

    @staticmethod
    def _delete_uploaded_object(storage: AvatarStorage, key: str, user_id: int) -> None:
        try:
            storage.delete_object(key)
        except ObjectStorageError:
            logger.warning("user_avatar_upload_compensation_failed user_id=%s", user_id)

    @staticmethod
    def _delete_replaced_object(storage: AvatarStorage, key: str, user_id: int) -> None:
        try:
            storage.delete_object(key)
        except ObjectStorageError:
            logger.warning("user_avatar_replaced_object_cleanup_failed user_id=%s", user_id)


def _validate_avatar(data: bytes, declared_content_type: str) -> tuple[str, str]:
    """按文件签名识别头像格式，并验证声明的 MIME 与文件内容一致。"""

    if not data or len(data) > MAX_AVATAR_UPLOAD_BYTES:
        raise InvalidUserProfileError("头像文件不能为空，且大小不能超过 2 MiB。")

    normalized_content_type = declared_content_type.split(";", maxsplit=1)[0].strip().lower()
    if data.startswith(PNG_SIGNATURE):
        detected_type, extension = "image/png", "png"
    elif data.startswith(JPEG_SIGNATURE):
        detected_type, extension = "image/jpeg", "jpg"
    elif (
        len(data) >= 12
        and data.startswith(WEBP_RIFF_SIGNATURE)
        and data[8:12] == WEBP_FORMAT_SIGNATURE
    ):
        detected_type, extension = "image/webp", "webp"
    else:
        raise InvalidUserProfileError("头像仅支持 PNG、JPEG 或 WebP 图片。")

    if normalized_content_type != detected_type:
        raise InvalidUserProfileError("头像文件类型与文件内容不匹配。")
    return detected_type, extension
