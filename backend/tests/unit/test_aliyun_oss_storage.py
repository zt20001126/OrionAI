from __future__ import annotations

import sys
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import pytest

from app.core.config import Settings
from app.infrastructure.storage import (
    AliyunOSSObjectStorage,
    ObjectNotFoundError,
    ObjectStorageError,
    ObjectStorageNotConfiguredError,
)


class FakeOssError(Exception):
    def __init__(self, message: str = "OSS request failed", status: int = 500) -> None:
        super().__init__(message)
        self.status = status


@dataclass
class FakeObjectResponse:
    data: bytes
    headers: dict[str, str]
    closed: bool = False

    def read(self, amount: int = -1) -> bytes:
        return self.data if amount < 0 else self.data[:amount]

    def close(self) -> None:
        self.closed = True


@dataclass
class FakeObjectSummary:
    key: str
    size: int
    last_modified: float


@dataclass
class FakeObjectList:
    object_list: list[FakeObjectSummary]
    is_truncated: bool
    next_marker: str | None


class FakeBucket:
    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, dict[str, str]]] = {}
        self.responses: list[FakeObjectResponse] = []
        self.list_calls: list[dict[str, Any]] = []
        self.list_results: list[FakeObjectList] = []
        self.next_error: FakeOssError | None = None

    def _raise_next_error(self) -> None:
        if self.next_error is not None:
            error = self.next_error
            self.next_error = None
            raise error

    def put_object(
        self,
        key: str,
        data: bytes,
        headers: dict[str, str] | None = None,
    ) -> None:
        self._raise_next_error()
        self.objects[key] = (data, dict(headers or {}))

    def get_object(self, key: str) -> FakeObjectResponse:
        self._raise_next_error()
        if key not in self.objects:
            raise FakeOssError("object missing", status=404)
        data, headers = self.objects[key]
        response = FakeObjectResponse(
            data,
            {**headers, "Content-Length": str(len(data))},
        )
        self.responses.append(response)
        return response

    def head_object(self, key: str) -> SimpleNamespace:
        self._raise_next_error()
        if key not in self.objects:
            raise FakeOssError("object missing", status=404)
        data, headers = self.objects[key]
        return SimpleNamespace(headers={**headers, "Content-Length": str(len(data))})

    def copy_object(self, bucket_name: str, source_key: str, target_key: str) -> None:
        del bucket_name
        self._raise_next_error()
        if source_key not in self.objects:
            raise FakeOssError("object missing", status=404)
        self.objects[target_key] = self.objects[source_key]

    def delete_object(self, key: str) -> None:
        self._raise_next_error()
        self.objects.pop(key, None)

    def list_objects(
        self,
        *,
        prefix: str,
        marker: str,
        max_keys: int,
    ) -> FakeObjectList:
        self._raise_next_error()
        self.list_calls.append({"prefix": prefix, "marker": marker, "max_keys": max_keys})
        return self.list_results.pop(0)


@pytest.fixture
def oss_storage(monkeypatch: pytest.MonkeyPatch) -> tuple[AliyunOSSObjectStorage, FakeBucket]:
    bucket = FakeBucket()
    fake_oss2 = SimpleNamespace(
        Auth=lambda access_key_id, access_key_secret: (access_key_id, access_key_secret),
        Bucket=lambda *_args: bucket,
        exceptions=SimpleNamespace(OssError=FakeOssError),
    )
    monkeypatch.setitem(sys.modules, "oss2", fake_oss2)
    settings = Settings(
        aliyun_oss_access_key_id="test-access-key",
        aliyun_oss_access_key_secret="test-access-secret",
        aliyun_oss_endpoint="https://oss-cn-hangzhou.aliyuncs.com/",
        aliyun_oss_bucket="private-test-bucket",
        aliyun_oss_object_prefix="/orion-test/",
        _env_file=None,
    )
    return AliyunOSSObjectStorage(settings), bucket


def test_oss_settings_are_optional_and_secret_is_masked() -> None:
    settings = Settings(_env_file=None)

    assert settings.aliyun_oss_configured is False
    assert "test-access-secret" not in repr(
        Settings(
            aliyun_oss_access_key_id="test-access-key",
            aliyun_oss_access_key_secret="test-access-secret",
            aliyun_oss_endpoint="https://oss-cn-hangzhou.aliyuncs.com",
            aliyun_oss_bucket="private-test-bucket",
            _env_file=None,
        )
    )


def test_oss_settings_load_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALIYUN_OSS_ACCESS_KEY_ID", "environment-key")
    monkeypatch.setenv("ALIYUN_OSS_ACCESS_KEY_SECRET", "environment-secret")
    monkeypatch.setenv("ALIYUN_OSS_ENDPOINT", "https://oss-cn-shanghai.aliyuncs.com")
    monkeypatch.setenv("ALIYUN_OSS_BUCKET", "environment-bucket")
    monkeypatch.setenv("ALIYUN_OSS_OBJECT_PREFIX", "orion-test")

    settings = Settings(_env_file=None)

    assert settings.aliyun_oss_configured is True
    assert settings.aliyun_oss_access_key_id.get_secret_value() == "environment-key"
    assert settings.aliyun_oss_object_prefix == "orion-test"


def test_adapter_rejects_missing_configuration_before_creating_bucket(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bucket_created = False

    def create_bucket(*_args: object) -> None:
        nonlocal bucket_created
        bucket_created = True

    monkeypatch.setitem(
        sys.modules,
        "oss2",
        SimpleNamespace(
            Auth=lambda *_args: object(),
            Bucket=create_bucket,
            exceptions=SimpleNamespace(OssError=FakeOssError),
        ),
    )

    with pytest.raises(ObjectStorageNotConfiguredError):
        AliyunOSSObjectStorage(Settings(_env_file=None))

    assert bucket_created is False


def test_adapter_rejects_insecure_endpoint_before_creating_bucket(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bucket_created = False

    def create_bucket(*_args: object) -> None:
        nonlocal bucket_created
        bucket_created = True

    monkeypatch.setitem(
        sys.modules,
        "oss2",
        SimpleNamespace(
            Auth=lambda *_args: object(),
            Bucket=create_bucket,
            exceptions=SimpleNamespace(OssError=FakeOssError),
        ),
    )
    settings = Settings(
        aliyun_oss_access_key_id="test-access-key",
        aliyun_oss_access_key_secret="test-access-secret",
        aliyun_oss_endpoint="http://oss-cn-hangzhou.aliyuncs.com",
        aliyun_oss_bucket="private-test-bucket",
        _env_file=None,
    )

    with pytest.raises(ValueError, match="HTTPS"):
        AliyunOSSObjectStorage(settings)

    assert bucket_created is False


def test_object_operations_use_root_prefix_and_normalize_results(
    oss_storage: tuple[AliyunOSSObjectStorage, FakeBucket],
) -> None:
    storage, bucket = oss_storage

    uploaded = storage.put_object(
        "documents/readme.txt",
        b"hello OSS",
        content_type="text/plain",
        metadata={"source": "unit-test"},
    )

    assert uploaded.key == "documents/readme.txt"
    assert uploaded.content_length == 9
    assert bucket.objects["orion-test/documents/readme.txt"] == (
        b"hello OSS",
        {
            "Content-Type": "text/plain",
            "x-oss-meta-source": "unit-test",
        },
    )

    downloaded = storage.get_object("documents/readme.txt")
    metadata = storage.head_object("documents/readme.txt")
    storage.copy_object("documents/readme.txt", "archive/readme.txt")
    storage.delete_object("documents/readme.txt")

    assert downloaded.data == b"hello OSS"
    assert downloaded.content_type == "text/plain"
    assert downloaded.user_metadata == {"source": "unit-test"}
    assert bucket.responses[0].closed is True
    assert metadata.content_length == 9
    assert metadata.content_type == "text/plain"
    assert "orion-test/archive/readme.txt" in bucket.objects
    assert "orion-test/documents/readme.txt" not in bucket.objects


def test_download_enforces_size_limit_and_closes_response(
    oss_storage: tuple[AliyunOSSObjectStorage, FakeBucket],
) -> None:
    storage, bucket = oss_storage
    storage.put_object("large.bin", b"012345", content_type="application/octet-stream")

    with pytest.raises(ObjectStorageError, match="读取上限"):
        storage.get_object("large.bin", max_bytes=5)

    assert bucket.responses[-1].closed is True


def test_missing_object_has_distinct_error(
    oss_storage: tuple[AliyunOSSObjectStorage, FakeBucket],
) -> None:
    storage, _bucket = oss_storage

    with pytest.raises(ObjectNotFoundError):
        storage.head_object("missing.txt")


def test_listing_uses_opaque_marker_and_returns_relative_keys(
    oss_storage: tuple[AliyunOSSObjectStorage, FakeBucket],
) -> None:
    storage, bucket = oss_storage
    bucket.list_results.extend(
        [
            FakeObjectList(
                [FakeObjectSummary("orion-test/docs/a.pdf", 12, 1_800_000_000.0)],
                True,
                "orion-test/docs/a.pdf",
            ),
            FakeObjectList(
                [FakeObjectSummary("orion-test/docs/b.pdf", 15, 1_800_000_001.0)],
                False,
                None,
            ),
        ]
    )

    first_page = storage.list_objects("docs/", max_keys=1)
    second_page = storage.list_objects("docs/", marker=first_page.next_marker, max_keys=1)

    assert first_page.items[0].key == "docs/a.pdf"
    assert first_page.items[0].content_length == 12
    assert first_page.is_truncated is True
    assert first_page.next_marker == "orion-test/docs/a.pdf"
    assert second_page.items[0].key == "docs/b.pdf"
    assert second_page.is_truncated is False
    assert bucket.list_calls == [
        {"prefix": "orion-test/docs/", "marker": "", "max_keys": 1},
        {
            "prefix": "orion-test/docs/",
            "marker": "orion-test/docs/a.pdf",
            "max_keys": 1,
        },
    ]


def test_sdk_error_is_sanitized_in_exception_and_log(
    oss_storage: tuple[AliyunOSSObjectStorage, FakeBucket],
    caplog: pytest.LogCaptureFixture,
) -> None:
    storage, bucket = oss_storage
    bucket.next_error = FakeOssError("secret=test-access-secret response=private", status=503)

    with caplog.at_level("WARNING"):
        with pytest.raises(ObjectStorageError) as error:
            storage.get_object("documents/readme.txt")

    assert "test-access-secret" not in str(error.value)
    assert "test-access-secret" not in caplog.text


def test_object_keys_cannot_escape_the_configured_prefix(
    oss_storage: tuple[AliyunOSSObjectStorage, FakeBucket],
) -> None:
    storage, _bucket = oss_storage

    with pytest.raises(ValueError, match="对象键"):
        storage.put_object("../outside.txt", b"data", content_type="text/plain")
