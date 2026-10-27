"""阿里云 OSS 通用对象存储适配器。"""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from typing import Any

from app.core.config import Settings
from app.infrastructure.storage.object_storage import (
    ObjectListingPage,
    ObjectMetadata,
    ObjectNotFoundError,
    ObjectStorageError,
    ObjectStorageNotConfiguredError,
    StoredObject,
)

logger = logging.getLogger(__name__)
_MAX_LIST_PAGE_SIZE = 1_000
_USER_METADATA_KEY_PATTERN = re.compile(r"^[a-z0-9-]+$")


class AliyunOSSObjectStorage:
    """对 OSS Bucket 的通用同步对象操作进行封装。"""

    def __init__(self, settings: Settings) -> None:
        if not settings.aliyun_oss_configured:
            raise ObjectStorageNotConfiguredError("阿里云 OSS 配置不完整。")

        import oss2

        self._oss2: Any = oss2
        access_key_id = settings.aliyun_oss_access_key_id.get_secret_value().strip()
        access_key_secret = settings.aliyun_oss_access_key_secret.get_secret_value().strip()
        endpoint = settings.aliyun_oss_endpoint.strip().rstrip("/")
        if not endpoint.lower().startswith("https://"):
            raise ValueError("阿里云 OSS endpoint 必须使用 HTTPS。")
        self._bucket_name = settings.aliyun_oss_bucket.strip()
        self._prefix = settings.aliyun_oss_object_prefix.strip("/")
        auth = oss2.Auth(access_key_id, access_key_secret)
        self._bucket = oss2.Bucket(auth, endpoint, self._bucket_name)

    def put_object(
        self,
        key: str,
        data: bytes,
        *,
        content_type: str,
        metadata: Mapping[str, str] | None = None,
    ) -> ObjectMetadata:
        """上传字节对象；对象键相对于配置的根前缀。"""
        object_key = self._resolve_key(key)
        if not content_type or "\r" in content_type or "\n" in content_type:
            raise ValueError("content_type 必须是有效的非空内容类型。")
        user_metadata = self._validate_metadata(metadata)
        headers = {"Content-Type": content_type}
        headers.update({f"x-oss-meta-{name}": value for name, value in user_metadata.items()})
        try:
            self._bucket.put_object(object_key, data, headers=headers)
        except self._oss2.exceptions.OssError as error:
            self._raise_storage_error("put_object", error)
        return ObjectMetadata(
            key=key,
            content_length=len(data),
            content_type=content_type,
            user_metadata=user_metadata,
        )

    def get_object(self, key: str, *, max_bytes: int | None = None) -> StoredObject:
        """下载对象；可选限制响应字节数，并始终关闭 OSS 响应。"""
        object_key = self._resolve_key(key)
        if max_bytes is not None and max_bytes < 0:
            raise ValueError("max_bytes 不能小于 0。")
        try:
            response = self._bucket.get_object(object_key)
        except self._oss2.exceptions.OssError as error:
            self._raise_storage_error("get_object", error, not_found=True)

        try:
            headers = _normalize_headers(response.headers)
            content_length = _content_length(headers)
            if max_bytes is not None and content_length > max_bytes:
                raise ObjectStorageError("OSS 对象超过读取上限。")
            data = response.read(-1 if max_bytes is None else max_bytes + 1)
            if max_bytes is not None and len(data) > max_bytes:
                raise ObjectStorageError("OSS 对象超过读取上限。")
            return StoredObject(
                key=key,
                data=data,
                content_type=headers.get("content-type"),
                user_metadata=_user_metadata(headers),
            )
        except self._oss2.exceptions.OssError as error:
            self._raise_storage_error("get_object", error, not_found=True)
        finally:
            response.close()

    def head_object(self, key: str) -> ObjectMetadata:
        """读取对象元数据；对象不存在时抛出 `ObjectNotFoundError`。"""
        object_key = self._resolve_key(key)
        try:
            result = self._bucket.head_object(object_key)
        except self._oss2.exceptions.OssError as error:
            self._raise_storage_error("head_object", error, not_found=True)
        return _metadata_from_headers(key, result.headers)

    def copy_object(self, source_key: str, target_key: str) -> None:
        """在当前 Bucket 内复制对象。"""
        source_object_key = self._resolve_key(source_key)
        target_object_key = self._resolve_key(target_key)
        try:
            self._bucket.copy_object(
                self._bucket_name,
                source_object_key,
                target_object_key,
            )
        except self._oss2.exceptions.OssError as error:
            self._raise_storage_error("copy_object", error, not_found=True)

    def delete_object(self, key: str) -> None:
        """删除对象；遵循 OSS 对重复删除的幂等语义。"""
        object_key = self._resolve_key(key)
        try:
            self._bucket.delete_object(object_key)
        except self._oss2.exceptions.OssError as error:
            self._raise_storage_error("delete_object", error)

    def list_objects(
        self,
        prefix: str = "",
        *,
        marker: str | None = None,
        max_keys: int = 100,
    ) -> ObjectListingPage:
        """按相对前缀分页列举对象；返回的 marker 可直接传入下一次调用。"""
        if not 1 <= max_keys <= _MAX_LIST_PAGE_SIZE:
            raise ValueError(f"max_keys 必须在 1 到 {_MAX_LIST_PAGE_SIZE} 之间。")
        object_prefix = self._resolve_prefix(prefix)
        try:
            result = self._bucket.list_objects(
                prefix=object_prefix,
                marker=marker or "",
                max_keys=max_keys,
            )
        except self._oss2.exceptions.OssError as error:
            self._raise_storage_error("list_objects", error)

        items = tuple(
            ObjectMetadata(
                key=self._relative_key(item.key),
                content_length=int(item.size),
                last_modified=float(item.last_modified),
            )
            for item in result.object_list
        )
        is_truncated = bool(result.is_truncated)
        return ObjectListingPage(
            items=items,
            is_truncated=is_truncated,
            next_marker=result.next_marker if is_truncated else None,
        )

    def _resolve_key(self, key: str) -> str:
        """校验相对对象键并应用配置的根前缀。"""
        if not isinstance(key, str) or not key or key.startswith("/") or "\\" in key:
            raise ValueError("对象键必须是非空相对对象键。")
        if any(part in {"", ".", ".."} for part in key.split("/")):
            raise ValueError("对象键必须是非空相对对象键。")
        return f"{self._prefix}/{key}" if self._prefix else key

    def _resolve_prefix(self, prefix: str) -> str:
        """将相对列举前缀放入配置根前缀，并保留尾部斜杠语义。"""
        if not isinstance(prefix, str) or prefix.startswith("/") or "\\" in prefix:
            raise ValueError("对象前缀必须是相对前缀。")
        normalized = prefix.rstrip("/")
        if normalized and any(part in {"", ".", ".."} for part in normalized.split("/")):
            raise ValueError("对象前缀必须是相对前缀。")
        if not normalized:
            return f"{self._prefix}/" if self._prefix else ""
        full_prefix = f"{self._prefix}/{normalized}" if self._prefix else normalized
        return f"{full_prefix}/" if prefix.endswith("/") else full_prefix

    def _relative_key(self, key: str) -> str:
        if not self._prefix:
            return key
        prefix = f"{self._prefix}/"
        return key.removeprefix(prefix)

    @staticmethod
    def _validate_metadata(metadata: Mapping[str, str] | None) -> dict[str, str]:
        normalized: dict[str, str] = {}
        for raw_name, value in (metadata or {}).items():
            name = raw_name.lower().removeprefix("x-oss-meta-")
            if not _USER_METADATA_KEY_PATTERN.fullmatch(name):
                raise ValueError("OSS 用户元数据名称格式不合法。")
            if not isinstance(value, str) or "\r" in value or "\n" in value:
                raise ValueError("OSS 用户元数据值必须是单行文本。")
            normalized[name] = value
        return normalized

    def _raise_storage_error(
        self,
        operation: str,
        error: Exception,
        *,
        not_found: bool = False,
    ) -> None:
        if not_found and getattr(error, "status", None) == 404:
            raise ObjectNotFoundError("OSS 对象不存在。") from None
        logger.warning(
            "aliyun_oss_operation_failed operation=%s bucket=%s error_type=%s",
            operation,
            self._bucket_name,
            type(error).__name__,
        )
        raise ObjectStorageError("阿里云 OSS 对象操作失败。") from None


def _normalize_headers(headers: Any) -> dict[str, str]:
    return {str(key).lower(): str(value) for key, value in headers.items()}


def _content_length(headers: Mapping[str, str]) -> int:
    try:
        content_length = int(headers.get("content-length", "0"))
    except ValueError:
        raise ObjectStorageError("OSS 对象长度元数据无效。") from None
    if content_length < 0:
        raise ObjectStorageError("OSS 对象长度元数据无效。")
    return content_length


def _user_metadata(headers: Mapping[str, str]) -> dict[str, str]:
    prefix = "x-oss-meta-"
    return {
        key.removeprefix(prefix): value for key, value in headers.items() if key.startswith(prefix)
    }


def _metadata_from_headers(key: str, headers: Any) -> ObjectMetadata:
    normalized = _normalize_headers(headers)
    return ObjectMetadata(
        key=key,
        content_length=_content_length(normalized),
        content_type=normalized.get("content-type"),
        user_metadata=_user_metadata(normalized),
    )
