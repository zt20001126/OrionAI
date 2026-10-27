"""验证图片结果 HTTP 接口的认证、权限和响应头。"""

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from typing import Annotated, Any

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.application import create_app
from app.core.config import Settings
from app.infrastructure.database.base import Base
from app.infrastructure.database.session import get_db_session
from app.infrastructure.storage.object_storage import StoredObject
from app.modules.agents.image_agent.dependencies import get_image_task_result_service
from app.modules.agents.image_agent.models import ImageTaskResult
from app.modules.agents.image_agent.service import ImageTaskResultService
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.conversations.models import Conversation
from app.modules.skills.models import Skill

PNG_BYTES = b"\x89PNG\r\n\x1a\nimage"


@asynccontextmanager
async def _test_lifespan(_application: FastAPI) -> AsyncIterator[None]:
    """结果接口测试不连接真实 Checkpointer 或模型。"""

    yield


@pytest.fixture
def image_result_client() -> Iterator[tuple[TestClient, dict[str, Any]]]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with Session(engine) as session:
        owner = User(account="image-owner@example.com", password_hash="hash")
        other_user = User(account="image-other@example.com", password_hash="hash")
        skill = Skill(code="image_agent", name="图片助手", type="agent", status="published")
        session.add_all([owner, other_user, skill])
        session.flush()
        conversation = Conversation(user_id=owner.id, skill_code=skill.code)
        session.add(conversation)
        session.flush()
        session.add_all(
            [
                ImageTaskResult(
                    task_result_id=1001,
                    user_id=owner.id,
                    conversation_id=conversation.id,
                    generation_status="succeeded",
                    input_data={},
                    result_data={"object_key": "images/private.png", "mime_type": "image/png"},
                ),
                ImageTaskResult(
                    task_result_id=1002,
                    user_id=owner.id,
                    conversation_id=conversation.id,
                    generation_status="failed",
                    input_data={},
                ),
            ]
        )
        session.commit()
        session.refresh(owner)
        session.refresh(other_user)

    state: dict[str, Any] = {"current_user": owner, "other_user": other_user}
    test_app = create_app(lifespan=_test_lifespan)

    def override_db_session() -> Iterator[Session]:
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    def override_current_user() -> User:
        return state["current_user"]

    class PrivateStorage:
        def get_object(self, key: str, *, max_bytes: int) -> StoredObject:
            assert key == "images/private.png"
            assert max_bytes > 0
            return StoredObject(key=key, data=PNG_BYTES, content_type="image/png")

    def override_image_service(
        session: Annotated[Session, Depends(get_db_session)],
    ) -> ImageTaskResultService:
        return ImageTaskResultService(
            session=session,
            settings=Settings(image_result_max_bytes=128),
            storage_factory=PrivateStorage,
        )

    test_app.dependency_overrides[get_db_session] = override_db_session
    test_app.dependency_overrides[get_current_user] = override_current_user
    test_app.dependency_overrides[get_image_task_result_service] = override_image_service
    try:
        with TestClient(test_app) as client:
            yield client, state
    finally:
        test_app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_image_result_endpoint_returns_only_owned_completed_images(
    image_result_client: tuple[TestClient, dict[str, Any]],
) -> None:
    client, state = image_result_client

    response = client.get("/api/v1/task-results/1001/image")

    assert response.status_code == 200
    assert response.content == PNG_BYTES
    assert response.headers["content-type"] == "image/png"
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert client.get("/api/v1/task-results/1002/image").status_code == 404
    assert client.get("/api/v1/task-results/9999/image").status_code == 404

    state["current_user"] = state["other_user"]
    assert client.get("/api/v1/task-results/1001/image").status_code == 404
