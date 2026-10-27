"""验证当前用户个人资料接口和头像写入流程。"""

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from typing import Annotated, Any

import pytest
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.application import create_app
from app.core.config import Settings
from app.infrastructure.database.base import Base
from app.infrastructure.database.session import get_db_session
from app.infrastructure.storage.object_storage import ObjectMetadata
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import DEFAULT_USER_AVATAR_URL, User
from app.modules.users.dependencies import get_users_service
from app.modules.users.service import UsersService

PNG_BYTES = b"\x89PNG\r\n\x1a\nvalid-png-data"


@asynccontextmanager
async def _test_lifespan(_application: FastAPI) -> AsyncIterator[None]:
    """个人资料 API 测试不连接模型或 PostgreSQL Checkpointer。"""

    yield


class FakeAvatarStorage:
    """在接口测试中模拟 OSS 对象边界并记录公开 ACL。"""

    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, str, bool]] = {}
        self.uploaded_keys: list[str] = []
        self.deleted_keys: list[str] = []

    def put_object(
        self,
        key: str,
        data: bytes,
        *,
        content_type: str,
        public_read: bool = False,
    ) -> ObjectMetadata:
        self.objects[key] = (data, content_type, public_read)
        self.uploaded_keys.append(key)
        return ObjectMetadata(key=key, content_length=len(data), content_type=content_type)

    def build_public_url(self, key: str) -> str:
        return f"https://profile-test.oss-cn-hangzhou.aliyuncs.com/orionai/{key}"

    def key_from_public_url(self, public_url: str) -> str | None:
        prefix = "https://profile-test.oss-cn-hangzhou.aliyuncs.com/orionai/"
        return public_url.removeprefix(prefix) if public_url.startswith(prefix) else None

    def delete_object(self, key: str) -> None:
        self.deleted_keys.append(key)
        self.objects.pop(key, None)


@pytest.fixture
def users_client() -> Iterator[tuple[TestClient, dict[str, Any]]]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with Session(engine) as session:
        owner = User(account="profile-owner@example.com", password_hash="hash")
        other_user = User(account="profile-other@example.com", password_hash="hash")
        session.add_all([owner, other_user])
        session.commit()
        session.refresh(owner)
        session.refresh(other_user)

    storage = FakeAvatarStorage()
    settings = Settings(_env_file=None)
    state: dict[str, Any] = {
        "current_user": owner,
        "other_user": other_user,
        "session_factory": session_factory,
        "storage": storage,
        "fail_commit": False,
        "authenticated": True,
    }
    test_app = create_app(lifespan=_test_lifespan)

    def override_db_session() -> Iterator[Session]:
        session = session_factory()
        if state["fail_commit"]:

            def fail_commit(_session: Session) -> None:
                raise SQLAlchemyError("simulated database error")

            event.listen(session, "before_commit", fail_commit)
        try:
            yield session
        finally:
            session.close()

    def override_current_user() -> User:
        if not state["authenticated"]:
            raise HTTPException(status_code=401, detail="请先登录。")
        return state["current_user"]

    def override_users_service(
        session: Annotated[Session, Depends(get_db_session)],
    ) -> UsersService:
        return UsersService(
            session=session,
            settings=settings,
            storage_factory=lambda: storage,
        )

    test_app.dependency_overrides[get_db_session] = override_db_session
    test_app.dependency_overrides[get_current_user] = override_current_user
    test_app.dependency_overrides[get_users_service] = override_users_service
    try:
        with TestClient(test_app) as client:
            yield client, state
    finally:
        test_app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_profile_returns_current_users_saved_fields_and_default_avatar(
    users_client: tuple[TestClient, dict[str, Any]],
) -> None:
    client, state = users_client

    response = client.get("/api/v1/users/me")

    assert response.status_code == 200
    payload = response.json()
    assert payload["account"] == "profile-owner@example.com"
    assert payload["nickname"] == "profile-owner"
    assert payload["avatar_url"] == DEFAULT_USER_AVATAR_URL
    assert payload["created_at"] is not None
    assert payload["last_login_at"] is None
    assert state["storage"].uploaded_keys == []


def test_profile_update_saves_avatar_key_and_returns_oss_url(
    users_client: tuple[TestClient, dict[str, Any]],
) -> None:
    client, state = users_client

    response = client.patch(
        "/api/v1/users/me",
        data={"nickname": "新昵称"},
        files={"avatar": ("portrait.png", PNG_BYTES, "image/png")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["nickname"] == "新昵称"
    assert payload["avatar_url"].startswith(
        "https://profile-test.oss-cn-hangzhou.aliyuncs.com/orionai/users/"
    )
    storage = state["storage"]
    assert len(storage.uploaded_keys) == 1
    uploaded_data, uploaded_content_type, is_public = storage.objects[storage.uploaded_keys[0]]
    assert uploaded_data == PNG_BYTES
    assert uploaded_content_type == "image/png"
    assert is_public is True

    with state["session_factory"]() as session:
        saved_user = session.scalar(select(User).where(User.id == state["current_user"].id))
        assert saved_user is not None
        assert saved_user.nickname == "新昵称"
        assert saved_user.avatar_key == storage.uploaded_keys[0]
        assert saved_user.avatar_url is None

    refreshed_profile = client.get("/api/v1/users/me")
    assert refreshed_profile.status_code == 200
    assert refreshed_profile.json()["avatar_url"] == payload["avatar_url"]


def test_profile_update_rejects_invalid_image_without_uploading(
    users_client: tuple[TestClient, dict[str, Any]],
) -> None:
    client, state = users_client

    response = client.patch(
        "/api/v1/users/me",
        data={"nickname": "新昵称"},
        files={"avatar": ("portrait.png", b"not an image", "image/png")},
    )

    assert response.status_code == 422
    assert state["storage"].uploaded_keys == []
    assert client.get("/api/v1/users/me").json()["nickname"] == "profile-owner"


def test_profile_update_rejects_avatar_over_two_mib(
    users_client: tuple[TestClient, dict[str, Any]],
) -> None:
    client, state = users_client
    oversized_png = PNG_BYTES + b"0" * (2 * 1024 * 1024)

    response = client.patch(
        "/api/v1/users/me",
        data={"nickname": "新昵称"},
        files={"avatar": ("portrait.png", oversized_png, "image/png")},
    )

    assert response.status_code == 422
    assert state["storage"].uploaded_keys == []


def test_profile_update_rejects_nickname_over_limit_without_uploading(
    users_client: tuple[TestClient, dict[str, Any]],
) -> None:
    client, state = users_client

    response = client.patch(
        "/api/v1/users/me",
        data={"nickname": "n" * 21},
    )

    assert response.status_code == 422
    assert state["storage"].uploaded_keys == []
    assert client.get("/api/v1/users/me").json()["nickname"] == "profile-owner"


def test_database_failure_removes_the_newly_uploaded_avatar(
    users_client: tuple[TestClient, dict[str, Any]],
) -> None:
    client, state = users_client
    state["fail_commit"] = True

    response = client.patch(
        "/api/v1/users/me",
        data={"nickname": "新昵称"},
        files={"avatar": ("portrait.png", PNG_BYTES, "image/png")},
    )

    assert response.status_code == 503
    storage = state["storage"]
    assert len(storage.uploaded_keys) == 1
    assert storage.deleted_keys == storage.uploaded_keys
    assert storage.objects == {}
    with state["session_factory"]() as session:
        saved_user = session.scalar(select(User).where(User.id == state["current_user"].id))
        assert saved_user is not None
        assert saved_user.nickname is None
        assert saved_user.avatar_key is None
        assert saved_user.avatar_url is None


def test_successful_avatar_replacement_deletes_the_previous_oss_object(
    users_client: tuple[TestClient, dict[str, Any]],
) -> None:
    client, state = users_client
    old_key = f"users/{state['current_user'].id}/avatars/old.png"
    state["current_user"].avatar_key = old_key
    state["storage"].objects[old_key] = (b"old-image", "image/png", True)
    with state["session_factory"]() as session:
        saved_user = session.get(User, state["current_user"].id)
        assert saved_user is not None
        saved_user.avatar_key = old_key
        saved_user.avatar_url = None
        session.commit()

    response = client.patch(
        "/api/v1/users/me",
        data={"nickname": "新昵称"},
        files={"avatar": ("portrait.png", PNG_BYTES, "image/png")},
    )

    assert response.status_code == 200
    assert old_key in state["storage"].deleted_keys
    assert old_key not in state["storage"].objects


def test_profile_update_requires_authentication(
    users_client: tuple[TestClient, dict[str, Any]],
) -> None:
    client, state = users_client
    state["authenticated"] = False

    response = client.patch("/api/v1/users/me", data={"nickname": "未授权"})

    assert response.status_code == 401
