import hashlib
import time
from collections.abc import Iterator
from contextlib import asynccontextmanager
from typing import Annotated

import pytest
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.application import create_app
from app.core.config import Settings
from app.infrastructure.database.base import Base
from app.infrastructure.database.session import get_db_session
from backend.app.infrastructure.email.email_sender import EmailDeliveryError
from app.infrastructure.redis.auth_state import AuthSession
from app.modules.auth import service as auth_service_module
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.auth.router import get_auth_service
from app.modules.auth.service import GENERIC_RESET_CODE_MESSAGE, AuthService


class InMemoryAuthStateStore:
    def __init__(self) -> None:
        self.codes: dict[tuple[str, str], dict[str, str | int | float]] = {}
        self.cooldowns: dict[tuple[str, str], float] = {}
        self.sessions: dict[str, AuthSession] = {}

    def start_code_cooldown(self, account: str, purpose: str) -> bool:
        key = (account, purpose)
        now = time.monotonic()
        if self.cooldowns.get(key, 0) > now:
            return False
        self.cooldowns[key] = now + 60
        return True

    def save_code(
        self,
        account: str,
        purpose: str,
        digest: str,
        ttl_seconds: int = 600,
    ) -> None:
        self.codes[(account, purpose)] = {
            "digest": digest,
            "attempts": 0,
            "expires_at": time.monotonic() + ttl_seconds,
        }

    def consume_code(self, account: str, purpose: str, digest: str) -> bool:
        key = (account, purpose)
        code_record = self.codes.get(key)
        if code_record is None or float(code_record["expires_at"]) <= time.monotonic():
            self.codes.pop(key, None)
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
    test_app = create_app(lifespan=_test_lifespan)
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

    def override_current_user(
        request: Request,
        session: Annotated[Session, Depends(get_db_session)],
    ) -> User:
        token = request.cookies.get(settings.auth_cookie_name)
        if not token:
            raise HTTPException(status_code=401, detail="请先登录。")
        token_digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        auth_session = state_store.get_session(token_digest)
        if auth_session is None:
            raise HTTPException(status_code=401, detail="请先登录。")
        user = session.scalar(select(User).where(User.account == auth_session.account))
        if user is None:
            raise HTTPException(status_code=401, detail="登录状态已失效，请重新登录。")
        password_fingerprint = hashlib.sha256(user.password_hash.encode("utf-8")).hexdigest()
        if password_fingerprint != auth_session.password_fingerprint:
            state_store.delete_session(token_digest)
            raise HTTPException(status_code=401, detail="登录状态已失效，请重新登录。")
        return user

    def capture_email(_settings: Settings, account: str, code: str, _purpose: str) -> None:
        sent_codes[account] = code

    monkeypatch.setattr(auth_service_module, "send_auth_code_email", capture_email)
    test_app.dependency_overrides[get_db_session] = override_db_session
    test_app.dependency_overrides[get_auth_service] = override_auth_service
    test_app.dependency_overrides[get_current_user] = override_current_user
    test_app.state.test_engine = engine
    test_app.state.auth_state_store = state_store

    try:
        with TestClient(test_app) as client:
            yield client, sent_codes
    finally:
        test_app.dependency_overrides.clear()
        del test_app.state.test_engine
        del test_app.state.auth_state_store
        Base.metadata.drop_all(engine)
        engine.dispose()


def request_code(client: TestClient, account: str, purpose: str = "register") -> str:
    response = client.post(
        "/api/auth/email-codes",
        json={"email": account, "purpose": purpose},
    )
    assert response.status_code == 202
    return response.json()["message"]


@asynccontextmanager
async def _test_lifespan(_application: FastAPI):
    """在认证 API 测试中跳过生产 PostgreSQL Checkpointer 生命周期。"""

    yield


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
    assert columns == {
        "id",
        "account",
        "password_hash",
        "created_at",
        "last_login_at",
        "nickname",
        "avatar_key",
        "avatar_url",
    }
    with Session(client.app.state.test_engine) as session:  # type: ignore[attr-defined]
        user = session.scalar(select(User).where(User.account == "person@example.com"))
        assert user is not None
        assert user.avatar_url is None
        assert user.avatar_key is None

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


def test_authenticated_password_change_invalidates_sessions_and_requires_new_login(
    auth_client: tuple[TestClient, dict[str, str]],
) -> None:
    client, sent_codes = auth_client
    create_account(client, sent_codes)
    old_token = client.cookies.get("orionai_session")
    assert old_token is not None

    code_response = client.post("/api/v1/users/me/password/code")
    assert code_response.status_code == 202
    code = sent_codes["person@example.com"]
    assert len(code) == 6 and code.isdecimal()

    state_store = client.app.state.auth_state_store  # type: ignore[attr-defined]
    expires_at = state_store.codes[("person@example.com", "password_change")]["expires_at"]
    assert time.monotonic() < float(expires_at) <= time.monotonic() + 300

    response = client.put(
        "/api/v1/users/me/password",
        json={
            "code": code,
            "new_password": "new secure password",
            "password_confirmation": "new secure password",
        },
    )

    assert response.status_code == 200
    assert 'orionai_session=""' in response.headers.get("set-cookie", "")
    assert client.get("/api/auth/session").json() == {"authenticated": False, "account": None}

    client.cookies.set("orionai_session", old_token)
    assert client.get("/api/auth/session").json() == {"authenticated": False, "account": None}
    assert (
        client.post(
            "/api/auth/login",
            json={"email": "person@example.com", "password": "correct horse battery"},
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/auth/login",
            json={"email": "person@example.com", "password": "new secure password"},
        ).status_code
        == 200
    )

    reused_code = client.put(
        "/api/v1/users/me/password",
        json={
            "code": code,
            "new_password": "another secure password",
            "password_confirmation": "another secure password",
        },
    )
    assert reused_code.status_code == 400


def test_password_change_rejects_wrong_and_expired_codes(
    auth_client: tuple[TestClient, dict[str, str]],
) -> None:
    client, sent_codes = auth_client
    create_account(client, sent_codes)
    assert client.post("/api/v1/users/me/password/code").status_code == 202
    code = sent_codes["person@example.com"]

    wrong_code = client.put(
        "/api/v1/users/me/password",
        json={
            "code": "000000" if code != "000000" else "000001",
            "new_password": "new secure password",
            "password_confirmation": "new secure password",
        },
    )
    assert wrong_code.status_code == 400

    state_store = client.app.state.auth_state_store  # type: ignore[attr-defined]
    state_store.codes[("person@example.com", "password_change")]["expires_at"] = 0
    expired_code = client.put(
        "/api/v1/users/me/password",
        json={
            "code": code,
            "new_password": "new secure password",
            "password_confirmation": "new secure password",
        },
    )
    assert expired_code.status_code == 400
    assert (
        client.post(
            "/api/auth/login",
            json={"email": "person@example.com", "password": "correct horse battery"},
        ).status_code
        == 200
    )


def test_new_password_code_replaces_the_previous_code(
    auth_client: tuple[TestClient, dict[str, str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generated_codes = iter((111111, 123456, 654321))
    monkeypatch.setattr(
        auth_service_module.secrets,
        "randbelow",
        lambda _limit: next(generated_codes),
    )
    client, sent_codes = auth_client
    create_account(client, sent_codes)
    assert client.post("/api/v1/users/me/password/code").status_code == 202
    old_code = sent_codes["person@example.com"]
    state_store = client.app.state.auth_state_store  # type: ignore[attr-defined]
    state_store.cooldowns[("person@example.com", "password_change")] = 0

    assert client.post("/api/v1/users/me/password/code").status_code == 202
    new_code = sent_codes["person@example.com"]
    assert new_code != old_code

    replaced_code = client.put(
        "/api/v1/users/me/password",
        json={
            "code": old_code,
            "new_password": "new secure password",
            "password_confirmation": "new secure password",
        },
    )
    assert replaced_code.status_code == 400

    accepted_code = client.put(
        "/api/v1/users/me/password",
        json={
            "code": new_code,
            "new_password": "new secure password",
            "password_confirmation": "new secure password",
        },
    )
    assert accepted_code.status_code == 200


def test_password_change_does_not_accept_a_client_selected_account(
    auth_client: tuple[TestClient, dict[str, str]],
) -> None:
    client, sent_codes = auth_client
    create_account(client, sent_codes)
    assert client.post("/api/v1/users/me/password/code").status_code == 202

    response = client.put(
        "/api/v1/users/me/password",
        json={
            "email": "another@example.com",
            "code": sent_codes["person@example.com"],
            "new_password": "new secure password",
            "password_confirmation": "new secure password",
        },
    )

    assert response.status_code == 422
    assert (
        client.post(
            "/api/auth/login",
            json={"email": "person@example.com", "password": "correct horse battery"},
        ).status_code
        == 200
    )


def test_password_settings_require_an_authenticated_session(
    auth_client: tuple[TestClient, dict[str, str]],
) -> None:
    client, sent_codes = auth_client
    create_account(client, sent_codes)
    client.cookies.clear()

    code_response = client.post("/api/v1/users/me/password/code")
    change_response = client.put(
        "/api/v1/users/me/password",
        json={
            "code": "123456",
            "new_password": "new secure password",
            "password_confirmation": "new secure password",
        },
    )

    assert code_response.status_code == 401
    assert change_response.status_code == 401


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


def test_password_change_rejects_current_password_and_preserves_surrounding_spaces(
    auth_client: tuple[TestClient, dict[str, str]],
) -> None:
    client, sent_codes = auth_client
    create_account(client, sent_codes)
    assert client.post("/api/v1/users/me/password/code").status_code == 202
    code = sent_codes["person@example.com"]

    same_password = client.put(
        "/api/v1/users/me/password",
        json={
            "code": code,
            "new_password": "correct horse battery",
            "password_confirmation": "correct horse battery",
        },
    )
    assert same_password.status_code == 422
    assert "不能与当前密码相同" in same_password.json()["detail"]

    password_with_spaces = "  new secure password  "
    changed_password = client.put(
        "/api/v1/users/me/password",
        json={
            "code": code,
            "new_password": password_with_spaces,
            "password_confirmation": password_with_spaces,
        },
    )
    assert changed_password.status_code == 200
    assert (
        client.post(
            "/api/auth/login",
            json={"email": "person@example.com", "password": password_with_spaces},
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/auth/login",
            json={"email": "person@example.com", "password": password_with_spaces.strip()},
        ).status_code
        == 401
    )


def test_password_change_limits_verification_attempts(
    auth_client: tuple[TestClient, dict[str, str]],
) -> None:
    client, sent_codes = auth_client
    create_account(client, sent_codes)
    assert client.post("/api/v1/users/me/password/code").status_code == 202
    code = sent_codes["person@example.com"]
    invalid_code = "000000" if code != "000000" else "000001"

    for _attempt in range(5):
        response = client.put(
            "/api/v1/users/me/password",
            json={
                "code": invalid_code,
                "new_password": "new secure password",
                "password_confirmation": "new secure password",
            },
        )
        assert response.status_code == 400

    blocked_correct_code = client.put(
        "/api/v1/users/me/password",
        json={
            "code": code,
            "new_password": "new secure password",
            "password_confirmation": "new secure password",
        },
    )
    assert blocked_correct_code.status_code == 400
