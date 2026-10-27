"""将简历照片保存在按用户隔离的私有对象键下。"""

from dataclasses import dataclass
from typing import Protocol

from app.infrastructure.storage.object_storage import (
    ObjectNotFoundError,
    ObjectStorageError,
    StoredObject,
)
from app.modules.resume.errors import ResumePhotoError, ResumePhotoStorageError


class ObjectStorage(Protocol):
    def put_object(
        self, key: str, data: bytes, *, content_type: str, **kwargs: object
    ) -> object: ...

    def get_object(self, key: str, *, max_bytes: int | None = None) -> StoredObject: ...

    def copy_object(self, source_key: str, target_key: str) -> None: ...

    def delete_object(self, key: str) -> None: ...


class ResumePhotoStorage(Protocol):
    def upload_staged(self, user_id: int, photo_id: str, data: bytes, mime_type: str) -> None: ...

    def promote_staged(self, user_id: int, photo_id: str) -> str: ...

    def read_saved(self, user_id: int, photo_id: str) -> tuple[bytes, str]: ...

    def delete_staged(self, user_id: int, photo_id: str) -> None: ...

    def delete_saved(self, user_id: int, photo_id: str, mime_type: str) -> None: ...


@dataclass(frozen=True)
class _PhotoKey:
    extension: str
    mime_type: str


_PHOTO_TYPES = {
    "image/png": _PhotoKey("png", "image/png"),
    "image/jpeg": _PhotoKey("jpg", "image/jpeg"),
}


class AliyunResumePhotoStorage:
    """只使用服务端生成的 ID 及当前认证用户 ID 构造 OSS 键。"""

    def __init__(self, storage: ObjectStorage) -> None:
        self._storage = storage

    def upload_staged(self, user_id: int, photo_id: str, data: bytes, mime_type: str) -> None:
        photo_type = self._photo_type(mime_type)
        try:
            self._storage.put_object(
                self._key(user_id, "staged", photo_id, photo_type),
                data,
                content_type=photo_type.mime_type,
            )
        except ObjectStorageError:
            raise ResumePhotoStorageError from None

    def promote_staged(self, user_id: int, photo_id: str) -> str:
        for photo_type in _PHOTO_TYPES.values():
            staged_key = self._key(user_id, "staged", photo_id, photo_type)
            try:
                stored = self._storage.get_object(staged_key, max_bytes=5 * 1024 * 1024)
            except ObjectNotFoundError:
                continue
            except ObjectStorageError:
                raise ResumePhotoStorageError from None
            if stored.content_type != photo_type.mime_type:
                raise ResumePhotoError from None
            try:
                self._storage.copy_object(
                    staged_key,
                    self._key(user_id, "saved", photo_id, photo_type),
                )
            except ObjectStorageError:
                raise ResumePhotoStorageError from None
            return photo_type.mime_type
        raise ResumePhotoError from None

    def read_saved(self, user_id: int, photo_id: str) -> tuple[bytes, str]:
        for photo_type in _PHOTO_TYPES.values():
            try:
                image = self._storage.get_object(
                    self._key(user_id, "saved", photo_id, photo_type), max_bytes=5 * 1024 * 1024
                )
            except ObjectNotFoundError:
                continue
            except ObjectStorageError:
                raise ResumePhotoStorageError from None
            if image.content_type != photo_type.mime_type:
                raise ResumePhotoError from None
            return image.data, photo_type.mime_type
        raise ResumePhotoError from None

    def delete_staged(self, user_id: int, photo_id: str) -> None:
        self._delete(user_id, "staged", photo_id)

    def delete_saved(self, user_id: int, photo_id: str, mime_type: str) -> None:
        photo_type = self._photo_type(mime_type)
        self._delete_key(self._key(user_id, "saved", photo_id, photo_type))

    def _delete(self, user_id: int, stage: str, photo_id: str) -> None:
        for photo_type in _PHOTO_TYPES.values():
            self._delete_key(self._key(user_id, stage, photo_id, photo_type))

    def _delete_key(self, key: str) -> None:
        try:
            self._storage.delete_object(key)
        except ObjectStorageError:
            raise ResumePhotoStorageError from None

    @staticmethod
    def _key(user_id: int, stage: str, photo_id: str, photo_type: _PhotoKey) -> str:
        return f"resumes/{user_id}/{stage}/{photo_id}.{photo_type.extension}"

    @staticmethod
    def _photo_type(mime_type: str) -> _PhotoKey:
        try:
            return _PHOTO_TYPES[mime_type]
        except KeyError:
            raise ResumePhotoError from None


class UnavailableResumePhotoStorage:
    """在 OSS 未配置时保留简历文本能力并明确拒绝照片操作。"""

    def upload_staged(self, user_id: int, photo_id: str, data: bytes, mime_type: str) -> None:
        raise ResumePhotoStorageError

    def promote_staged(self, user_id: int, photo_id: str) -> str:
        raise ResumePhotoStorageError

    def read_saved(self, user_id: int, photo_id: str) -> tuple[bytes, str]:
        raise ResumePhotoStorageError

    def delete_staged(self, user_id: int, photo_id: str) -> None:
        raise ResumePhotoStorageError

    def delete_saved(self, user_id: int, photo_id: str, mime_type: str) -> None:
        raise ResumePhotoStorageError
