"""Gitee OAuth 登录与账号绑定业务流程。"""

from __future__ import annotations

import json
import secrets
from datetime import UTC, datetime
from urllib.parse import urlencode

import httpx
from redis.exceptions import RedisError
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.infrastructure.redis.auth_state import RedisAuthStateStore
from app.modules.auth.errors import (
    AuthUnavailableError,
    OAuthAccountConflictError,
    OAuthEmailConflictError,
    OAuthError,
)
from app.modules.auth.models.user import User
from app.modules.auth.repositories import gitee as gitee_repository
from app.modules.auth.repositories import users as repository
from app.modules.auth.services.auth import AuthService

OAUTH_STATE_TTL_SECONDS = 600
GITEE_AUTHORIZE_URL = "https://gitee.com/oauth/authorize"
GITEE_TOKEN_URL = "https://gitee.com/oauth/token"
GITEE_USER_URL = "https://gitee.com/api/v5/user"


class GiteeOAuthService:
    """封装 Gitee 远程授权及本地身份关联；调用方：Gitee OAuth Router。"""

    def __init__(
        self, session: Session, state_store: RedisAuthStateStore, settings: Settings
    ) -> None:
        self._session = session
        self._state_store = state_store
        self._settings = settings

    def authorization_url(self, current_user: User | None = None) -> str:
        """生成 Gitee 授权地址。

        输入：绑定时提供当前用户；输出：授权 URL；调用方：Gitee 登录/绑定路由。
        """
        if (
            not self._settings.gitee_client_id
            or not self._settings.gitee_client_secret.get_secret_value()
        ):
            raise AuthUnavailableError
        state = secrets.token_urlsafe(32)
        context = (
            {"purpose": "bind", "user_id": current_user.id}
            if current_user
            else {"purpose": "login"}
        )
        try:
            self._state_store.save_oauth_state(state, json.dumps(context), OAUTH_STATE_TTL_SECONDS)
        except RedisError as error:
            raise AuthUnavailableError from error
        parameters = urlencode(
            {
                "client_id": self._settings.gitee_client_id,
                "redirect_uri": self._settings.gitee_redirect_uri,
                "response_type": "code",
                "scope": "user_info",
                "state": state,
            }
        )
        return f"{GITEE_AUTHORIZE_URL}?{parameters}"

    def callback(
        self, code: str | None, state: str | None, current_user: User | None
    ) -> str | None:
        """消费一次性 state 并处理回调。

        输入：授权码、state 和当前用户；输出：登录令牌或绑定空值；调用方：Gitee 回调路由。
        """
        if not state:
            raise OAuthError("Gitee 授权状态无效，请重试。")
        try:
            raw_context = self._state_store.consume_oauth_state(state)
        except RedisError as error:
            raise AuthUnavailableError from error
        if raw_context is None:
            raise OAuthError("Gitee 授权状态已过期或已使用，请重试。")
        if not code:
            raise OAuthError("Gitee 授权未完成，请重试。")
        try:
            context = json.loads(raw_context)
        except (TypeError, ValueError) as error:
            raise OAuthError("Gitee 授权状态无效，请重试。") from error
        if not isinstance(context, dict):
            raise OAuthError("Gitee 授权状态无效，请重试。")
        if context.get("purpose") == "bind":
            if current_user is None or context.get("user_id") != current_user.id:
                raise OAuthError("绑定期间登录身份发生变化，请重新发起绑定。")
        elif context.get("purpose") != "login":
            raise OAuthError("Gitee 授权状态与当前操作不匹配，请重试。")

        profile = self._fetch_profile(code)
        provider_user_id = str(profile["id"])
        if context["purpose"] == "bind":
            self._bind(current_user, provider_user_id)
            return None
        user = self._identify_or_create(profile, provider_user_id)
        return AuthService(self._session, self._state_store, self._settings).create_session(user)

    def discard_state(self, state: str | None) -> None:
        """消费用户拒绝授权的 state；输入：回调 state；输出：无；调用方：Gitee 回调路由。"""
        if not state:
            return
        try:
            self._state_store.consume_oauth_state(state)
        except RedisError as error:
            raise AuthUnavailableError from error

    def _fetch_profile(self, code: str) -> dict[str, object]:
        """用授权码读取 Gitee 用户资料。

        输入：授权码；输出：用户资料；调用方：OAuth 回调；令牌仅留在服务端。
        """
        try:
            with httpx.Client(timeout=10.0) as client:
                token_response = client.post(
                    GITEE_TOKEN_URL,
                    data={
                        "grant_type": "authorization_code",
                        "code": code,
                        "client_id": self._settings.gitee_client_id,
                        "client_secret": self._settings.gitee_client_secret.get_secret_value(),
                        "redirect_uri": self._settings.gitee_redirect_uri,
                    },
                )
                token_response.raise_for_status()
                token_payload = token_response.json()
                if not isinstance(token_payload, dict):
                    raise OAuthError("Gitee 令牌响应格式无效。")
                access_token = token_payload.get("access_token")
                if not isinstance(access_token, str) or not access_token:
                    raise OAuthError("Gitee 未返回有效授权令牌。")
                profile_response = client.get(GITEE_USER_URL, params={"access_token": access_token})
                profile_response.raise_for_status()
                profile = profile_response.json()
        except OAuthError:
            raise
        except (httpx.HTTPError, ValueError) as error:
            raise OAuthError("无法连接 Gitee 或解析授权信息，请稍后重试。") from error
        provider_user_id = profile.get("id") if isinstance(profile, dict) else None
        if (
            not isinstance(profile, dict)
            or isinstance(provider_user_id, bool)
            or not isinstance(provider_user_id, (str, int))
            or not str(provider_user_id)
        ):
            raise OAuthError("Gitee 用户资料格式无效。")
        return profile

    def _identify_or_create(self, profile: dict[str, object], provider_user_id: str) -> User:
        """按 Gitee ID 识别用户并处理邮箱冲突。

        输入：用户资料和稳定 ID；输出：本地用户；调用方：OAuth 回调。
        """
        try:
            user = gitee_repository.get_user_by_gitee_id(self._session, provider_user_id)
            if user is not None:
                user.last_login_at = datetime.now(UTC)
                self._session.commit()
                return user
            email = profile.get("email")
            if (
                isinstance(email, str)
                and email.strip()
                and repository.get_user(self._session, email.strip().lower()) is not None
            ):
                raise OAuthEmailConflictError
            nickname_value = profile.get("name") or profile.get("login")
            avatar_value = profile.get("avatar_url")
            user = gitee_repository.create_gitee_user(
                self._session,
                provider_user_id,
                nickname_value if isinstance(nickname_value, str) else None,
                avatar_value if isinstance(avatar_value, str) else None,
                datetime.now(UTC),
            )
            if user is not None:
                return user
            user = gitee_repository.get_user_by_gitee_id(self._session, provider_user_id)
            if user is not None:
                return user
            raise AuthUnavailableError
        except OAuthEmailConflictError:
            self._session.rollback()
            raise
        except IntegrityError as error:
            self._session.rollback()
            try:
                user = gitee_repository.get_user_by_gitee_id(self._session, provider_user_id)
                if user is not None:
                    return user
                email = profile.get("email")
                if (
                    isinstance(email, str)
                    and email.strip()
                    and repository.get_user(self._session, email.strip().lower()) is not None
                ):
                    raise OAuthEmailConflictError from error
            except OAuthEmailConflictError:
                raise
            except SQLAlchemyError as lookup_error:
                self._session.rollback()
                raise AuthUnavailableError from lookup_error
            raise AuthUnavailableError from error
        except SQLAlchemyError as error:
            self._session.rollback()
            raise AuthUnavailableError from error

    def _bind(self, current_user: User | None, provider_user_id: str) -> None:
        """绑定 Gitee 身份到当前用户。

        输入：本地用户与 Gitee 用户 ID；输出：无；调用方：OAuth 回调。
        """
        if current_user is None:
            raise OAuthError("请先登录后再绑定 Gitee 账号。")
        try:
            existing = gitee_repository.get_user_by_gitee_id(self._session, provider_user_id)
            if existing is not None:
                if existing.id == current_user.id:
                    return
                raise OAuthAccountConflictError
            if current_user.gitee_id is not None and current_user.gitee_id != provider_user_id:
                raise OAuthAccountConflictError
            gitee_repository.bind_gitee_id(self._session, current_user, provider_user_id)
        except OAuthAccountConflictError:
            self._session.rollback()
            raise
        except IntegrityError as error:
            self._session.rollback()
            raise OAuthAccountConflictError from error
        except SQLAlchemyError as error:
            self._session.rollback()
            raise AuthUnavailableError from error
