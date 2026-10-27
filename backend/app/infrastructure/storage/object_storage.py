"""对象存储适配器使用的稳定类型与错误。"""

from collections.abc import Mapping
from dataclasses import dataclass, field


class ObjectStorageError(RuntimeError):
    """对象存储操作失败，异常消息不包含上游响应或凭据信息。"""


class ObjectStorageNotConfiguredError(ObjectStorageError):
    """对象存储适配器缺少必要配置。"""


class ObjectNotFoundError(ObjectStorageError):
    """指定对象不存在或当前适配器无法访问该对象。"""


@dataclass(frozen=True, slots=True)
class ObjectMetadata:
    """对象键、大小、内容类型和用户元数据。"""

    key: str
    content_length: int
    content_type: str | None = None
    user_metadata: Mapping[str, str] = field(default_factory=dict)
    last_modified: float | None = None


@dataclass(frozen=True, slots=True)
class StoredObject:
    """从对象存储读取的对象内容及其元数据。"""

    key: str
    data: bytes
    content_type: str | None = None
    user_metadata: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ObjectListingPage:
    """对象列举结果及用于请求下一页的 OSS marker。"""

    items: tuple[ObjectMetadata, ...]
    is_truncated: bool
    next_marker: str | None
