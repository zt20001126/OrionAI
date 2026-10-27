from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.application import create_app
from app.infrastructure.database.base import Base
from app.infrastructure.database.session import get_db_session
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.skills.models import Skill, UserSkill


@asynccontextmanager
async def _test_lifespan(_application: FastAPI) -> AsyncIterator[None]:
    """技能接口测试无需启动模型或真实 Checkpointer。"""

    yield


@pytest.fixture
def skills_client() -> Iterator[tuple[TestClient, dict[str, Any]]]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with Session(engine) as session:
        owner = User(account="skills-owner@example.com", password_hash="hash")
        other = User(account="skills-other@example.com", password_hash="hash")
        session.add_all([owner, other])
        session.commit()
        session.refresh(owner)
        session.refresh(other)

    state: dict[str, Any] = {
        "users": {"current": owner, "other": other},
        "session_factory": session_factory,
    }
    test_app = create_app(lifespan=_test_lifespan)

    def override_db_session() -> Iterator[Session]:
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    def override_current_user() -> User:
        return state["users"]["current"]

    test_app.dependency_overrides[get_db_session] = override_db_session
    test_app.dependency_overrides[get_current_user] = override_current_user
    try:
        with TestClient(test_app) as client:
            yield client, state
    finally:
        test_app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()


def _create_skill(
    state: dict[str, Any],
    *,
    code: str,
    name: str,
    skill_type: str = "agent",
    status: str = "published",
) -> int:
    with state["session_factory"]() as session:
        skill = Skill(code=code, name=name, type=skill_type, status=status)
        session.add(skill)
        session.commit()
        session.refresh(skill)
        return skill.id


def _add_relation(state: dict[str, Any], user: User, skill_id: int) -> None:
    with state["session_factory"]() as session:
        session.add(UserSkill(user_id=user.id, skill_id=skill_id))
        session.commit()


def test_market_lists_published_skills_with_user_state_and_filters(
    skills_client: tuple[TestClient, dict[str, Any]],
) -> None:
    client, state = skills_client
    general_id = _create_skill(state, code="test_general", name="General helper")
    tool_id = _create_skill(state, code="test_tool", name="Image tool", skill_type="tool")
    _create_skill(state, code="test_hidden", name="Hidden helper", status="disabled")
    _add_relation(state, state["users"]["current"], general_id)
    _add_relation(state, state["users"]["other"], tool_id)

    response = client.get("/api/v1/skills")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 2
    items = {item["code"]: item for item in payload["items"]}
    assert items["test_general"]["is_added"] is True
    assert items["test_tool"]["is_added"] is False
    assert "test_hidden" not in items

    catalog = client.get("/api/v1/skills", params={"include_disabled": True}).json()
    catalog_items = {item["code"]: item for item in catalog["items"]}
    assert catalog["total"] == 3
    assert catalog_items["test_hidden"]["status"] == "disabled"

    filtered_by_type = client.get("/api/v1/skills", params={"type": "tool"})
    assert [item["code"] for item in filtered_by_type.json()["items"]] == ["test_tool"]

    filtered_by_keyword = client.get("/api/v1/skills", params={"keyword": "General"})
    assert [item["code"] for item in filtered_by_keyword.json()["items"]] == ["test_general"]

    invalid_type = client.get("/api/v1/skills", params={"type": "workflow"})
    assert invalid_type.status_code == 422

    state["users"]["current"] = state["users"]["other"]
    other_view = client.get("/api/v1/skills").json()
    other_items = {item["code"]: item for item in other_view["items"]}
    assert other_items["test_tool"]["is_added"] is True
    assert other_items["test_general"]["is_added"] is False


def test_market_pagination_is_stable_and_returns_total(
    skills_client: tuple[TestClient, dict[str, Any]],
) -> None:
    client, state = skills_client
    for index in range(5):
        _create_skill(
            state,
            code=f"page_{index}",
            name=f"Page item {index}",
        )

    first = client.get("/api/v1/skills", params={"page": 1, "page_size": 2}).json()
    first_repeat = client.get("/api/v1/skills", params={"page": 1, "page_size": 2}).json()
    second = client.get("/api/v1/skills", params={"page": 2, "page_size": 2}).json()

    first_ids = [item["id"] for item in first["items"]]
    second_ids = [item["id"] for item in second["items"]]
    assert first["total"] == 5
    assert first["page"] == 1
    assert first["page_size"] == 2
    assert first_ids == [item["id"] for item in first_repeat["items"]]
    assert len(first_ids) == len(second_ids) == 2
    assert set(first_ids).isdisjoint(second_ids)


def test_skill_detail_only_exposes_published_skills(
    skills_client: tuple[TestClient, dict[str, Any]],
) -> None:
    client, state = skills_client
    skill_id = _create_skill(state, code="detail", name="Detail skill")
    disabled_id = _create_skill(
        state, code="detail_disabled", name="Disabled skill", status="disabled"
    )

    response = client.get(f"/api/v1/skills/{skill_id}")
    assert response.status_code == 200
    assert response.json()["id"] == str(skill_id)
    assert response.json()["is_added"] is False
    assert client.get(f"/api/v1/skills/{disabled_id}").status_code == 404
    assert client.get("/api/v1/skills/1").status_code == 404


def test_add_skill_and_reject_duplicate_missing_or_disabled(
    skills_client: tuple[TestClient, dict[str, Any]],
) -> None:
    client, state = skills_client
    skill_id = _create_skill(state, code="add_me", name="Add me")
    disabled_id = _create_skill(state, code="disabled_add", name="Disabled", status="disabled")

    added = client.post("/api/v1/users/me/skills", json={"skill_id": str(skill_id)})
    assert added.status_code == 201
    assert added.json()["is_added"] is True
    assert (
        client.post("/api/v1/users/me/skills", json={"skill_id": str(skill_id)}).status_code == 409
    )
    assert (
        client.post("/api/v1/users/me/skills", json={"skill_id": "1"}).status_code
        == 404
    )
    assert (
        client.post("/api/v1/users/me/skills", json={"skill_id": str(disabled_id)}).status_code
        == 404
    )
    assert client.post("/api/v1/users/me/skills", json={"skill_id": "invalid"}).status_code == 422
    extra_user_id = client.post(
        "/api/v1/users/me/skills",
        json={"skill_id": str(skill_id), "user_id": 2},
    )
    assert extra_user_id.status_code == 422


def test_my_skills_are_private_and_hide_disabled_definitions(
    skills_client: tuple[TestClient, dict[str, Any]],
) -> None:
    client, state = skills_client
    own_id = _create_skill(state, code="my_skill", name="My skill")
    other_id = _create_skill(state, code="other_skill", name="Other skill")
    hidden_id = _create_skill(state, code="my_disabled", name="Hidden", status="disabled")
    _add_relation(state, state["users"]["current"], own_id)
    _add_relation(state, state["users"]["current"], hidden_id)
    _add_relation(state, state["users"]["other"], other_id)

    response = client.get("/api/v1/users/me/skills")

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["items"]] == [str(own_id)]
    assert response.json()["items"][0]["is_added"] is True


def test_removal_only_deletes_the_current_users_relation(
    skills_client: tuple[TestClient, dict[str, Any]],
) -> None:
    client, state = skills_client
    skill_id = _create_skill(state, code="shared_skill", name="Shared")
    _add_relation(state, state["users"]["current"], skill_id)
    _add_relation(state, state["users"]["other"], skill_id)

    removed = client.delete(f"/api/v1/users/me/skills/{skill_id}")
    assert removed.status_code == 204
    assert removed.content == b""
    assert client.delete(f"/api/v1/users/me/skills/{skill_id}").status_code == 404
    assert client.get(f"/api/v1/skills/{skill_id}").json()["is_added"] is False

    state["users"]["current"] = state["users"]["other"]
    assert client.get(f"/api/v1/skills/{skill_id}").json()["is_added"] is True
    assert client.get("/api/v1/users/me/skills").json()["items"][0]["id"] == str(skill_id)


@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        ("get", "/api/v1/skills", None),
        ("get", "/api/v1/skills/1", None),
        ("get", "/api/v1/users/me/skills", None),
        ("post", "/api/v1/users/me/skills", {"skill_id": "1"}),
        ("delete", "/api/v1/users/me/skills/1", None),
    ],
)
def test_all_skill_endpoints_require_login(
    method: str,
    path: str,
    payload: dict[str, str] | None,
) -> None:
    with TestClient(create_app(lifespan=_test_lifespan)) as client:
        response = client.request(method, path, json=payload)

    assert response.status_code == 401
