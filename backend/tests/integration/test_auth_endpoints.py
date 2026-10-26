from collections.abc import Iterator
from typing import Annotated

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import Settings
from app.infrastructure.database.base import Base
from app.infrastructure.database.session import get_db_session
from app.infrastructure.email_sender import EmailDeliveryError
from app.infrastructure.redis.auth_state import AuthSession
from app.main import app
from app.modules.auth import service as auth_service_module
from app.modules.auth.router import get_auth_service
from app.modules.auth.service import GENERIC_RESET_CODE_MESSAGE, AuthService


class InMemoryAuthStateStore:
    def __init__(self) -> None:
        self.codes: dict[tuple[str, str], dict[str, str | int]] = {}
        self.cooldowns: set[tuple[str, str]] = set()
        self.sessions: dict[str, AuthSession] = {}

    def start_code_cooldown(self, account: str, purpose: str) -> bool:
        key = (account, purpose)
        if key in self.cooldowns:
            return False
        self.cooldowns.add(key)
        return True

    def save_code(self, account: str, purpose: str, digest: str) -> None:
        self.codes[(account, purpose)] = {"digest": digest, "attempts": 0}

    def consume_code(self, account: str, purpose: str, digest: str) -> bool:
        key = (account, purpose)
        code_record = self.codes.get(key)
        if code_record is None:
            return False
        if code_record["digest"] != digest:
            attempts = int(code_record["attempts"]) + 1
            if attempts >= 5:
                del self.codes[key]
            else:
                code_record["attempts"] = attempts
            return False
        del self.codes[key]
        return True

    def delete_code(self, account: str, purpose: str) -> None:
        self.codes.pop((account, purpose), None)

    def save_session(self, token_digest: str, session: AuthSession, ttl_seconds: int) -> None:
        self.sessions[token_digest] = session

    def get_session(self, token_digest: str) -> AuthSession | None:
        return self.sessions.get(token_digest)

    def delete_session(self, token_digest: str) -> None:
        self.sessions.pop(token_digest, None)


@pytest.fixture
def auth_client(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[TestClient, dict[str, str]]]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    test_session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    state_store = InMemoryAuthStateStore()
    sent_codes: dict[str, str] = {}
    settings = Settings(
        environment="test",
        auth_code_pepper="test-only-pepper",
        auth_cookie_secure=False,
        auth_session_ttl_seconds=3600,
    )

    def override_db_session() -> Iterator[Session]:
        session = test_session_factory()
        try:
            yield session
        finally:
            session.close()

    def override_auth_service(
        session: Annotated[Session, Depends(get_db_session)],
    ) -> AuthService:
        return AuthService(session, state_store, settings)

    def capture_email(_settings: Settings, account: str, code: str, _purpose: str) -> None:
        sent_codes[account] = code

    monkeypatch.setattr(auth_service_module, "send_auth_code_email", capture_email)
    app.dependency_overrides[get_db_session] = override_db_session
    app.dependency_overrides[get_auth_service] = override_auth_service
    app.state.test_engine = engine

    try:
        with TestClient(app) as client:
            yield client, sent_codes
    finally:
        app.dependency_overrides.clear()
        del app.state.test_engine
        Base.metadata.drop_all(engine)
        engine.dispose()


def request_code(client: TestClient, account: str, purpose: str = "register") -> str:
    response = client.post(
        "/api/auth/email-codes",
        json={"email": account, "purpose": purpose},
    )
    assert response.status_code == 202
    return response.json()["message"]


def create_account(
    client: TestClient,
    sent_codes: dict[str, str],
    account: str = "person@example.com",
    password: str = "correct horse battery",
) -> dict[str, str]:
    request_code(client, account)
    normalized_account = account.strip().lower()
    response = client.post(
        "/api/auth/register",
        json={
            "email": account,
            "code": sent_codes[normalized_account],
            "password": password,
            "password_confirmation": password,
        },
    )
    assert response.status_code == 200
    return response.json()


def test_register_creates_one_user_and_uses_httponly_cookie(
    auth_client: tuple[TestClient, dict[str, str]],
) -> None:
    client, sent_codes = auth_client
    response = create_account(client, sent_codes, "  Person@Example.com ")

    assert response == {"account": "person@example.com"}
    set_cookie = client.cookies.get("orionai_session")
    assert set_cookie is not None
    assert "orionai_session" not in response

    session_response = client.get("/api/auth/session")
    assert session_response.json() == {
        "authenticated": True,
        "account": "person@example.com",
    }

    columns = {
        column["name"]
        for column in inspect(client.app.state.test_engine).get_columns("users")  # type: ignore[attr-defined]
    }
    assert columns == {"account", "password_hash", "created_at", "last_login_at"}

    logout_response = client.post("/api/auth/logout")
    assert logout_response.status_code == 200
    assert client.get("/api/auth/session").json() == {"authenticated": False, "account": None}


def test_email_codes_are_single_use_and_rate_limited(
    auth_client: tuple[TestClient, dict[str, str]],
) -> None:
    client, sent_codes = auth_client
    request_code(client, "person@example.com")
    code = sent_codes["person@example.com"]

    too_soon = client.post(
        "/api/auth/email-codes",
        json={"email": "person@example.com", "purpose": "register"},
    )
    assert too_soon.status_code == 429

    first_register = client.post(
        "/api/auth/register",
        json={
            "email": "person@example.com",
            "code": code,
            "password": "correct horse battery",
            "password_confirmation": "correct horse battery",
        },
    )
    second_register = client.post(
        "/api/auth/register",
        json={
            "email": "person@example.com",
            "code": code,
            "password": "correct horse battery",
            "password_confirmation": "correct horse battery",
        },
    )
    assert first_register.status_code == 200
    assert second_register.status_code == 409


def test_unknown_password_reset_request_does_not_send_email(
    auth_client: tuple[TestClient, dict[str, str]],
) -> None:
    client, sent_codes = auth_client

    response = client.post(
        "/api/auth/email-codes",
        json={"email": "unknown@example.com", "purpose": "password_reset"},
    )

    assert response.status_code == 202
    assert response.json() == {"message": GENERIC_RESET_CODE_MESSAGE}
    assert sent_codes == {}


def test_failed_email_send_removes_code_but_keeps_cooldown(
    auth_client: tuple[TestClient, dict[str, str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _sent_codes = auth_client

    def fail_delivery(*_args: object, **_kwargs: object) -> None:
        raise EmailDeliveryError("SMTP unavailable")

    monkeypatch.setattr(auth_service_module, "send_auth_code_email", fail_delivery)
    failed_send = client.post(
        "/api/auth/email-codes",
        json={"email": "person@example.com", "purpose": "register"},
    )
    retry = client.post(
        "/api/auth/email-codes",
        json={"email": "person@example.com", "purpose": "register"},
    )

    assert failed_send.status_code == 503
    assert retry.status_code == 429


def test_password_reset_invalidates_existing_session(
    auth_client: tuple[TestClient, dict[str, str]],
) -> None:
    client, sent_codes = auth_client
    create_account(client, sent_codes)
    request_code(client, "person@example.com", "password_reset")
    reset_code = sent_codes["person@example.com"]
    reset_response = client.post(
        "/api/auth/password-reset",
        json={
            "email": "person@example.com",
            "code": reset_code,
            "new_password": "new secure password",
            "password_confirmation": "new secure password",
        },
    )

    assert reset_response.status_code == 200
    reused_code_response = client.post(
        "/api/auth/password-reset",
        json={
            "email": "person@example.com",
            "code": reset_code,
            "new_password": "another secure password",
            "password_confirmation": "another secure password",
        },
    )
    assert reused_code_response.status_code == 400
    assert client.get("/api/auth/session").json() == {"authenticated": False, "account": None}

    old_password_response = client.post(
        "/api/auth/login",
        json={"email": "person@example.com", "password": "correct horse battery"},
    )
    new_password_response = client.post(
        "/api/auth/login",
        json={"email": "person@example.com", "password": "new secure password"},
    )
    assert old_password_response.status_code == 401
    assert new_password_response.status_code == 200


def test_login_errors_do_not_disclose_account_existence(
    auth_client: tuple[TestClient, dict[str, str]],
) -> None:
    client, sent_codes = auth_client
    create_account(client, sent_codes)
    wrong_password = client.post(
        "/api/auth/login",
        json={"email": "person@example.com", "password": "wrong password"},
    )
    unknown_account = client.post(
        "/api/auth/login",
        json={"email": "missing@example.com", "password": "wrong password"},
    )

    assert wrong_password.status_code == unknown_account.status_code == 401
    assert wrong_password.json() == unknown_account.json()
