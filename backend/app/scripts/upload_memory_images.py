"""按统一命名将本地训练图片上传到 OSS 并登记公开链接。"""

import argparse
import logging
from pathlib import Path

from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.core.config import get_settings
from app.infrastructure.database.session import SessionLocal
from app.infrastructure.storage.aliyun_oss import AliyunOSSObjectStorage
from app.infrastructure.storage.object_storage import ObjectNotFoundError, ObjectStorageError
from app.modules.memory_training import repository

logger = logging.getLogger(__name__)
SUPPORTED_IMAGES = {
    ".png": ("png", "image/png"),
    ".jpg": ("jpg", "image/jpeg"),
    ".jpeg": ("jpg", "image/jpeg"),
}
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
JPEG_SIGNATURE = b"\xff\xd8\xff"
OBJECT_DIRECTORY = "memory-training"


def main() -> None:
    """上传指定目录图片，使用 4 位序号对象名，并幂等登记数据库链接。"""

    parser = argparse.ArgumentParser(description="上传记忆训练图片并登记 OSS 公开链接")
    parser.add_argument("directory", type=Path, help="本地图片素材目录")
    source_directory = parser.parse_args().directory
    if not source_directory.is_dir():
        raise SystemExit("指定的图片素材目录不存在。")

    image_paths = sorted(
        (
            path
            for path in source_directory.iterdir()
            if path.is_file() and path.suffix.lower() in SUPPORTED_IMAGES
        ),
        key=lambda path: path.name.casefold(),
    )
    if not image_paths:
        raise SystemExit("目录中没有 PNG 或 JPEG 图片。")

    settings = get_settings()
    storage = AliyunOSSObjectStorage(settings)
    for index, image_path in enumerate(image_paths, start=1):
        extension, content_type = SUPPORTED_IMAGES[image_path.suffix.lower()]
        object_name = f"memory-training-{index:04d}.{extension}"
        object_key = f"{OBJECT_DIRECTORY}/{object_name}"
        image_bytes = image_path.read_bytes()
        _validate_image_signature(image_bytes, content_type)
        uploaded = _upload_if_needed(storage, object_key, image_bytes, content_type)
        image_url = storage.build_public_url(object_key)
        try:
            with SessionLocal() as session:
                existing_image = repository.get_image_by_url(session, image_url)
                if existing_image is None:
                    repository.add_image(session, image_url)
                    session.commit()
                    action = "已登记"
                else:
                    action = "已存在"
        except IntegrityError:
            with SessionLocal() as session:
                existing_image = repository.get_image_by_url(session, image_url)
            if existing_image is None:
                if uploaded:
                    storage.delete_object(object_key)
                raise
            action = "已存在"
        except SQLAlchemyError:
            if uploaded:
                try:
                    storage.delete_object(object_key)
                except ObjectStorageError:
                    logger.exception(
                        "memory_training_upload_compensation_failed object_key=%s", object_key
                    )
            raise
        print(f"{image_path.name} -> {object_name} ({action}) {image_url}")


def _upload_if_needed(
    storage: AliyunOSSObjectStorage,
    object_key: str,
    image_bytes: bytes,
    content_type: str,
) -> bool:
    """若对象已存在则验证字节一致，避免静默覆盖素材。"""

    try:
        existing_object = storage.get_object(object_key)
    except ObjectNotFoundError:
        storage.put_object(
            object_key,
            image_bytes,
            content_type=content_type,
            public_read=True,
        )
        return True
    except ObjectStorageError:
        raise
    if existing_object.data != image_bytes:
        raise RuntimeError(f"OSS 对象已存在且内容不同，拒绝覆盖：{object_key}")
    # 再次设置对象级 ACL，保证重复导入也会把相同素材设为公开读。
    storage.put_object(
        object_key,
        image_bytes,
        content_type=content_type,
        public_read=True,
    )
    return False


def _validate_image_signature(image_bytes: bytes, content_type: str) -> None:
    """按文件签名校验扩展名对应的真实图片类型。"""

    is_valid = (
        image_bytes.startswith(PNG_SIGNATURE)
        if content_type == "image/png"
        else image_bytes.startswith(JPEG_SIGNATURE)
    )
    if not is_valid:
        raise ValueError("图片扩展名和实际文件格式不匹配。")


if __name__ == "__main__":
    main()
