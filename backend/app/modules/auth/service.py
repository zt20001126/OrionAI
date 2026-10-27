from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import UTC, datetime
from typing import Protocol

from redis.exceptions import RedisError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import Settings
from backend.app.infrastructure.email.email_sender import EmailDeliveryError, send_auth_code_email
from app.infrastructure.redis.auth_state import (
    CODE_TTL_SECONDS,
    PASSWORD_CHANGE_CODE_TTL_SECONDS,
    AuthSession,
)
from app.modules.auth import repository
from app.modules.auth.errors import (
    AccountExistsError,
    AuthUnavailableError,
    InvalidCodeError,
    InvalidCredentialsError,
    PasswordPolicyError,
    RateLimitError,
)
from app.modules.auth.models import User

SCRYPT_N = 2**15
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_KEY_LENGTH = 64
SCRYPT_SALT_LENGTH = 16
SCRYPT_MAX_MEMORY = 128 * 1024 * 1024
DUMMY_PASSWORD_HASH = (
    "scrypt$32768$8$1$61f3c779180a7d0cbb91e6d4ef31a222$"
    "56a0e284436e6f5665db53e8a8487b13cba1220cedfbfc1c51f8955107336c4f"
    "6b4fd6cb9906894b6e487a8720b9d87af83868bcb1ce8f1eacd60a5e3486a302"
)
GENERIC_RESET_CODE_MESSAGE = "如果邮箱已注册，验证码将发送到邮箱。"


class AuthStateStore(Protocol):
    def start_code_cooldown(self, account: str, purpose: str) -> bool: ...

    def save_code(
        self,
        account: str,
        purpose: str,
        digest: str,
        ttl_seconds: int = CODE_TTL_SECONDS,
    ) -> None: ...

    def consume_code(self, account: str, purpose: str, digest: str) -> bool: ...

    def delete_code(self, account: str, purpose: str) -> None: ...

    def save_session(self, token_digest: str, session: AuthSession, ttl_seconds: int) -> None: ...

    def get_session(self, token_digest: str) -> AuthSession | None: ...

    def delete_session(self, token_digest: str) -> None: ...


def normalize_email(email: str) -> str:
    return email.strip().lower()


def hash_password(password: str, salt: bytes | None = None) -> str:
    actual_salt = salt or secrets.token_bytes(SCRYPT_SALT_LENGTH)
    password_digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=actual_salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        dklen=SCRYPT_KEY_LENGTH,
        maxmem=SCRYPT_MAX_MEMORY,
    )
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${actual_salt.hex()}${password_digest.hex()}"


def verify_password(password: str, encoded_hash: str | None) -> bool:
    candidate_hash = encoded_hash or DUMMY_PASSWORD_HASH
    try:
        algorithm, n_text, r_text, p_text, salt_text, digest_text = candidate_hash.split("$")
        if algorithm != "scrypt":
            return False
        expected_digest = bytes.fromhex(digest_text)
        actual_digest = hashlib.scrypt(
            password.encode("utf-8"),
            salt=bytes.fromhex(salt_text),
            n=int(n_text),
            r=int(r_text),
            p=int(p_text),
            dklen=len(expected_digest),
            maxmem=SCRYPT_MAX_MEMORY,
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual_digest, expected_digest)


def _verification_digest(pepper: str, purpose: str, account: str, code: str) -> str:
    message = f"{purpose}:{account}:{code}".encode()
    return hmac.new(pepper.encode("utf-8"), message, hashlib.sha256).hexdigest()


def _password_fingerprint(password_hash: str) -> str:
    return hashlib.sha256(password_hash.encode("utf-8")).hexdigest()


def _token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class AuthService:
    def __init__(self, session: Session, state_store: AuthStateStore, settings: Settings) -> None:
        self._session = session
        self._state_store = state_store
        self._settings = settings

    def request_email_code(self, account: str, purpose: str) -> str:
        account = normalize_email(account)
        user = self._get_user(account)
        if purpose == "password_reset" and user is None:
            return GENERIC_RESET_CODE_MESSAGE
        if purpose == "register" and user is not None:
            raise AccountExistsError
        self._send_email_code(account, purpose)
        return "验证码已发送。" if purpose == "register" else GENERIC_RESET_CODE_MESSAGE

    def request_password_change_code(self, account: str) -> str:
        """向当前认证用户的绑定邮箱发送限时修改密码验证码。"""

        account = normalize_email(account)
        if self._get_user(account) is None:
            raise InvalidCredentialsError
        self._send_email_code(
            account,
            "password_change",
            ttl_seconds=PASSWORD_CHANGE_CODE_TTL_SECONDS,
        )
        return "验证码已发送。"

    def register(self, account: str, code: str, password: str) -> tuple[str, str]:
        account = normalize_email(account)
        if self._get_user(account) is not None:
            raise AccountExistsError
        self._consume_code(account, "register", code)
        now = datetime.now(UTC)
        try:
            user = repository.create_user(
                self._session,
                account,
                hash_password(password),
                now,
            )
        except SQLAlchemyError as error:
            self._session.rollback()
            raise AuthUnavailableError from error
        if user is None:
            raise AccountExistsError
        return account, self._create_session(user)

    def login(self, account: str, password: str) -> tuple[str, str]:
        account = normalize_email(account)
        user = self._get_user(account)
        if not verify_password(password, user.password_hash if user else None):
            raise InvalidCredentialsError
        assert user is not None
        now = datetime.now(UTC)
        try:
            repository.update_last_login(self._session, user, now)
        except SQLAlchemyError as error:
            self._session.rollback()
            raise AuthUnavailableError from error
        return account, self._create_session(user)

    def get_session_account(self, token: str | None) -> str | None:
        if not token:
            return None
        token_digest = _token_digest(token)
        try:
            auth_session = self._state_store.get_session(token_digest)
            if auth_session is None:
                return None
            user = self._get_user(auth_session.account)
            if user is None or not hmac.compare_digest(
                _password_fingerprint(user.password_hash),
                auth_session.password_fingerprint,
            ):
                self._state_store.delete_session(token_digest)
                return None
            return user.account
        except RedisError as error:
            raise AuthUnavailableError from error

    def logout(self, token: str | None) -> None:
        if token:
            try:
                self._state_store.delete_session(_token_digest(token))
            except RedisError as error:
                raise AuthUnavailableError from error

    def reset_password(self, account: str, code: str, new_password: str) -> None:
        account = normalize_email(account)
        user = self._get_user(account)
        self._consume_code(account, "password_reset", code)
        if user is None:
            raise InvalidCodeError
        try:
            repository.update_password(self._session, user, hash_password(new_password))
        except SQLAlchemyError as error:
            self._session.rollback()
            raise AuthUnavailableError from error

    def change_password(self, account: str, code: str, new_password: str) -> None:
        """验证当前用户邮箱验证码并更新密码哈希，使旧会话指纹失效。"""

        if not 8 <= len(new_password) <= 64 or not new_password.strip():
            raise PasswordPolicyError("密码长度须为 8 到 64 个字符，且不能仅由空格组成。")
        user = self._get_user(normalize_email(account))
        if user is None:
            raise InvalidCredentialsError
        if verify_password(new_password, user.password_hash):
            raise PasswordPolicyError("新密码不能与当前密码相同。")
        self._consume_code(user.account, "password_change", code)
        try:
            repository.update_password(self._session, user, hash_password(new_password))
        except SQLAlchemyError as error:
            self._session.rollback()
            raise AuthUnavailableError from error

    def _get_user(self, account: str) -> User | None:
        try:
            return repository.get_user(self._session, account)
        except SQLAlchemyError as error:
            self._session.rollback()
            raise AuthUnavailableError from error

    def _consume_code(self, account: str, purpose: str, code: str) -> None:
        if not self._settings.auth_code_pepper:
            raise AuthUnavailableError
        digest = _verification_digest(self._settings.auth_code_pepper, purpose, account, code)
        try:
            if not self._state_store.consume_code(account, purpose, digest):
                raise InvalidCodeError
        except RedisError as error:
            raise AuthUnavailableError from error

    def _send_email_code(
        self,
        account: str,
        purpose: str,
        *,
        ttl_seconds: int = CODE_TTL_SECONDS,
    ) -> None:
        if not self._settings.auth_code_pepper:
            raise AuthUnavailableError

        code = f"{secrets.randbelow(1_000_000):06d}"
        digest = _verification_digest(self._settings.auth_code_pepper, purpose, account, code)
        try:
            if not self._state_store.start_code_cooldown(account, purpose):
                raise RateLimitError
            self._state_store.save_code(account, purpose, digest, ttl_seconds)
        except RedisError as error:
            raise AuthUnavailableError from error

        try:
            send_auth_code_email(self._settings, account, code, purpose)
        except EmailDeliveryError as error:
            try:
                self._state_store.delete_code(account, purpose)
            except RedisError as redis_error:
                raise AuthUnavailableError from redis_error
            raise AuthUnavailableError from error

    def _create_session(self, user: User) -> str:
        token = secrets.token_urlsafe(32)
        session = AuthSession(
            account=user.account,
            password_fingerprint=_password_fingerprint(user.password_hash),
        )
        try:
            self._state_store.save_session(
                _token_digest(token),
                session,
                self._settings.auth_session_ttl_seconds,
            )
        except RedisError as error:
            raise AuthUnavailableError from error
        return token
