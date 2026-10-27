"""对象存储适配器及其通用类型。"""

from app.infrastructure.storage.aliyun_oss import AliyunOSSObjectStorage
from app.infrastructure.storage.object_storage import (
    ObjectListingPage,
    ObjectMetadata,
    ObjectNotFoundError,
    ObjectStorageError,
    ObjectStorageNotConfiguredError,
    StoredObject,
)

__all__ = [
    "AliyunOSSObjectStorage",
    "ObjectListingPage",
    "ObjectMetadata",
    "ObjectNotFoundError",
    "ObjectStorageError",
    "ObjectStorageNotConfiguredError",
    "StoredObject",
]
