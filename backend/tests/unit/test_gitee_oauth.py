from __future__ import annotations

from collections.abc import Iterator
from urllib.parse import parse_qs, urlsplit

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.infrastructure.redis.auth_state import AuthSession
from app.modules.auth.errors import OAuthAccountConflictError, OAuthEmailConflictError, OAuthError
from app.modules.auth.models import User
from app.modules.auth.services.auth import AuthService
from app.modules.auth.services.gitee import GiteeOAuthService


class MemoryOAuthStateStore:
    def __init__(self) -> None:
        self.states: dict[str, str] = {}
        self.sessions: dict[str, AuthSession] = {}

    def save_oauth_state(self, state: str, context: str, ttl_seconds: int) -> None:
        self.states[state] = context

    def consume_oauth_state(self, state: str) -> str | None:
        return self.states.pop(state, None)

    def save_session(self, token_digest: str, session: AuthSession, ttl_seconds: int) -> None:
        self.sessions[token_digest] = session

    def get_session(self, token_digest: str) -> AuthSession | None:
        return self.sessions.get(token_digest)

    def delete_session(self, token_digest: str) -> None:
        self.sessions.pop(token_digest, None)


@pytest.fixture
def oauth_context() -> Iterator[tuple[Session, MemoryOAuthStateStore, GiteeOAuthService]]:
    engine = create_engine("sqlite://")
    User.__table__.create(engine)
    with Session(engine) as session:
        store = MemoryOAuthStateStore()
        settings = Settings(
            gitee_client_id="test-client",
            gitee_client_secret="test-secret",
            gitee_redirect_uri="http://localhost:8000/api/v1/auth/gitee/callback",
        )
        service = GiteeOAuthService(session, store, settings)  # type: ignore[arg-type]
        yield session, store, service
    engine.dispose()


def _new_state(service: GiteeOAuthService) -> str:
    query = parse_qs(urlsplit(service.authorization_url()).query)
    return query["state"][0]


def test_authorization_url_saves_a_one_time_state(
    oauth_context: tuple[Session, MemoryOAuthStateStore, GiteeOAuthService],
) -> None:
    _session, store, service = oauth_context

    authorization_url = service.authorization_url()
    query = parse_qs(urlsplit(authorization_url).query)
    state = query["state"][0]

    assert query["scope"] == ["user_info"]
    assert store.consume_oauth_state(state) == '{"purpose": "login"}'
    assert store.consume_oauth_state(state) is None


def test_login_creates_gitee_user_in_users_table_and_session_resolves(
    oauth_context: tuple[Session, MemoryOAuthStateStore, GiteeOAuthService],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session, store, service = oauth_context
    monkeypatch.setattr(
        service,
        "_fetch_profile",
        lambda _code: {"id": 12345, "login": "orion", "name": "Orion"},
    )

    token = service.callback("authorization-code", _new_state(service), None)
    user = session.scalar(select(User))
    session_user = AuthService(session, store, Settings()).get_session_user(token)  # type: ignore[arg-type]

    assert token
    assert user is not None
    assert user.gitee_id == "12345"
    assert user.is_guest is False
    assert user.account is None and user.password_hash is None
    assert session_user is not None and session_user.id == user.id


def test_repeated_login_reuses_the_user_row(
    oauth_context: tuple[Session, MemoryOAuthStateStore, GiteeOAuthService],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session, _store, service = oauth_context
    monkeypatch.setattr(service, "_fetch_profile", lambda _code: {"id": 12345})

    first = service.callback("first-code", _new_state(service), None)
    second = service.callback("second-code", _new_state(service), None)

    assert first and second
    assert session.scalar(select(func.count(User.id))) == 1


def test_login_rejects_existing_email_without_signing_in_or_linking(
    oauth_context: tuple[Session, MemoryOAuthStateStore, GiteeOAuthService],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session, _store, service = oauth_context
    email_user = User(account="same@example.com", password_hash="hash", is_guest=False)
    session.add(email_user)
    session.commit()
    monkeypatch.setattr(
        service,
        "_fetch_profile",
        lambda _code: {"id": 987, "email": "same@example.com"},
    )

    with pytest.raises(OAuthEmailConflictError):
        service.callback("authorization-code", _new_state(service), None)

    assert session.scalar(select(func.count(User.id))) == 1
    assert email_user.gitee_id is None


def test_bind_preserves_email_credentials_and_sets_gitee_id(
    oauth_context: tuple[Session, MemoryOAuthStateStore, GiteeOAuthService],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session, _store, service = oauth_context
    user = User(account="owner@example.com", password_hash="hash", is_guest=False)
    session.add(user)
    session.commit()
    original_password_hash = user.password_hash
    monkeypatch.setattr(service, "_fetch_profile", lambda _code: {"id": 4321})

    state = parse_qs(urlsplit(service.authorization_url(user)).query)["state"][0]
    result = service.callback("authorization-code", state, user)

    assert result is None
    assert user.gitee_id == "4321"
    assert user.account == "owner@example.com"
    assert user.password_hash == original_password_hash
    assert session.scalar(select(func.count(User.id))) == 1


def test_bind_rejects_gitee_identity_owned_by_another_user(
    oauth_context: tuple[Session, MemoryOAuthStateStore, GiteeOAuthService],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session, _store, service = oauth_context
    owner = User(account="owner@example.com", password_hash="hash", is_guest=False)
    other = User(account="other@example.com", password_hash="hash", is_guest=False, gitee_id="4321")
    session.add_all([owner, other])
    session.commit()
    monkeypatch.setattr(service, "_fetch_profile", lambda _code: {"id": 4321})
    state = parse_qs(urlsplit(service.authorization_url(owner)).query)["state"][0]

    with pytest.raises(OAuthAccountConflictError):
        service.callback("authorization-code", state, owner)

    assert owner.gitee_id is None
    assert other.gitee_id == "4321"


def test_bind_rejects_a_session_switch_after_authorization(
    oauth_context: tuple[Session, MemoryOAuthStateStore, GiteeOAuthService],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session, _store, service = oauth_context
    owner = User(account="owner@example.com", password_hash="hash", is_guest=False)
    other = User(account="other@example.com", password_hash="hash", is_guest=False)
    session.add_all([owner, other])
    session.commit()
    monkeypatch.setattr(service, "_fetch_profile", lambda _code: pytest.fail("不得读取 Gitee 资料"))
    state = parse_qs(urlsplit(service.authorization_url(owner)).query)["state"][0]

    with pytest.raises(OAuthError, match="身份发生变化"):
        service.callback("authorization-code", state, other)


def test_fetch_profile_exchanges_code_and_reads_gitee_user(
    oauth_context: tuple[Session, MemoryOAuthStateStore, GiteeOAuthService],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _session, _store, service = oauth_context
    calls: dict[str, object] = {}

    class FakeResponse:
        def __init__(self, payload: dict[str, object]) -> None:
            self._payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return self._payload

    class FakeClient:
        def __enter__(self) -> FakeClient:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def post(self, url: str, *, data: dict[str, str]) -> FakeResponse:
            calls["token_url"] = url
            calls["token_data"] = data
            return FakeResponse({"access_token": "private-access-token"})

        def get(self, url: str, *, params: dict[str, str]) -> FakeResponse:
            calls["user_url"] = url
            calls["user_params"] = params
            return FakeResponse({"id": 765, "login": "orion"})

    monkeypatch.setattr(
        "app.modules.auth.services.gitee.httpx.Client", lambda **_kwargs: FakeClient()
    )

    profile = service._fetch_profile("authorization-code")

    assert profile == {"id": 765, "login": "orion"}
    assert calls["token_url"] == "https://gitee.com/oauth/token"
    assert calls["token_data"]["grant_type"] == "authorization_code"  # type: ignore[index]
    assert calls["user_url"] == "https://gitee.com/api/v5/user"
    assert calls["user_params"] == {"access_token": "private-access-token"}
