from __future__ import annotations

import hashlib

from app.infrastructure.storage.object_storage import ObjectNotFoundError, StoredObject
from app.scripts.upload_memory_images import _upload_if_needed


class InMemoryStorage:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.put_calls: list[tuple[str, bytes, str, bool]] = []

    def get_object(self, object_key: str) -> StoredObject:
        try:
            data = self.objects[object_key]
        except KeyError:
            raise ObjectNotFoundError("object missing") from None
        return StoredObject(key=object_key, data=data)

    def put_object(
        self,
        object_key: str,
        data: bytes,
        *,
        content_type: str,
        public_read: bool,
    ) -> None:
        self.objects[object_key] = data
        self.put_calls.append((object_key, data, content_type, public_read))


def test_changed_default_asset_uses_a_new_content_addressed_object() -> None:
    storage = InMemoryStorage()
    legacy_key = "memory-training/memory-training-0001.png"
    storage.objects[legacy_key] = b"previous image bytes"
    image_bytes = b"updated image bytes"

    stored_key, uploaded = _upload_if_needed(
        storage,
        legacy_key,
        image_bytes,
        "image/png",
    )

    expected_key = (
        f"memory-training/memory-training-0001-{hashlib.sha256(image_bytes).hexdigest()}.png"
    )
    assert stored_key == expected_key
    assert uploaded is True
    assert storage.objects[legacy_key] == b"previous image bytes"
    assert storage.objects[expected_key] == image_bytes

    repeated_key, repeated_upload = _upload_if_needed(
        storage,
        legacy_key,
        image_bytes,
        "image/png",
    )

    assert repeated_key == expected_key
    assert repeated_upload is False


def test_reimport_of_same_content_reuses_content_addressed_object() -> None:
    storage = InMemoryStorage()
    image_bytes = b"same image bytes"
    object_key = "memory-training/memory-training-0001.png"

    first_key, first_upload = _upload_if_needed(storage, object_key, image_bytes, "image/png")
    second_key, second_upload = _upload_if_needed(storage, object_key, image_bytes, "image/png")

    assert first_key == second_key == object_key
    assert first_upload is True
    assert second_upload is False
    assert len(storage.put_calls) == 2
