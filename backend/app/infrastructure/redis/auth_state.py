from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from redis import Redis

CODE_TTL_SECONDS = 600
PASSWORD_CHANGE_CODE_TTL_SECONDS = 300
CODE_COOLDOWN_SECONDS = 60
CODE_MAX_ATTEMPTS = 5
VERIFY_CODE_SCRIPT = """
local saved_digest = redis.call('HGET', KEYS[1], 'digest')
if not saved_digest then
    return 0
end
if saved_digest ~= ARGV[1] then
    local attempts = redis.call('HINCRBY', KEYS[1], 'attempts', 1)
    if attempts >= tonumber(ARGV[2]) then
        redis.call('DEL', KEYS[1])
        return 2
    end
    return 1
end
redis.call('DEL', KEYS[1])
return 3
"""
CONSUME_OAUTH_STATE_SCRIPT = """
local value = redis.call('GET', KEYS[1])
if value then
    redis.call('DEL', KEYS[1])
end
return value
"""


@dataclass(frozen=True)
class AuthSession:
    account: str | None = None
    password_fingerprint: str | None = None
    user_id: int | None = None


class RedisAuthStateStore:
    def __init__(self, client: Redis, key_prefix: str = "orionai:auth") -> None:
        self._client = client
        self._key_prefix = key_prefix

    def start_code_cooldown(self, account: str, purpose: str) -> bool:
        return bool(
            self._client.set(
                self._code_key("cooldown", account, purpose),
                "1",
                ex=CODE_COOLDOWN_SECONDS,
                nx=True,
            )
        )

    def save_code(
        self,
        account: str,
        purpose: str,
        digest: str,
        ttl_seconds: int = CODE_TTL_SECONDS,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("验证码有效期必须大于 0。")
        key = self._code_key("code", account, purpose)
        with self._client.pipeline(transaction=True) as pipeline:
            pipeline.hset(key, mapping={"digest": digest, "attempts": "0"})
            pipeline.expire(key, ttl_seconds)
            pipeline.execute()

    def consume_code(self, account: str, purpose: str, digest: str) -> bool:
        result = self._client.eval(
            VERIFY_CODE_SCRIPT,
            1,
            self._code_key("code", account, purpose),
            digest,
            CODE_MAX_ATTEMPTS,
        )
        return int(result) == 3

    def delete_code(self, account: str, purpose: str) -> None:
        self._client.delete(self._code_key("code", account, purpose))

    def save_session(
        self,
        token_digest: str,
        session: AuthSession,
        ttl_seconds: int,
    ) -> None:
        payload = json.dumps(
            {
                "account": session.account,
                "password_fingerprint": session.password_fingerprint,
                "user_id": session.user_id,
            }
        )
        self._client.setex(self._session_key(token_digest), ttl_seconds, payload)

    def get_session(self, token_digest: str) -> AuthSession | None:
        payload = self._client.get(self._session_key(token_digest))
        if payload is None:
            return None
        try:
            session_data = json.loads(payload)
            if not isinstance(session_data, dict):
                raise ValueError("Invalid session payload")
            account = session_data.get("account")
            password_fingerprint = session_data.get("password_fingerprint")
            user_id = session_data.get("user_id")
            if account is not None and not isinstance(account, str):
                raise ValueError("Invalid session account")
            if password_fingerprint is not None and not isinstance(password_fingerprint, str):
                raise ValueError("Invalid session fingerprint")
            if user_id is not None and (not isinstance(user_id, int) or user_id <= 0):
                raise ValueError("Invalid session user ID")
            if account is None and user_id is None:
                raise ValueError("Session has no identity")
            if account is not None and password_fingerprint is None:
                raise ValueError("Invalid session payload")
            return AuthSession(
                account=account,
                password_fingerprint=password_fingerprint,
                user_id=user_id,
            )
        except (KeyError, TypeError, ValueError):
            self.delete_session(token_digest)
            return None

    def delete_session(self, token_digest: str) -> None:
        self._client.delete(self._session_key(token_digest))

    def save_oauth_state(self, state: str, context: str, ttl_seconds: int) -> None:
        """保存一次性 OAuth 上下文；调用方：第三方登录 Service。"""
        self._client.set(self._oauth_state_key(state), context, ex=ttl_seconds)

    def consume_oauth_state(self, state: str) -> str | None:
        """原子读取并删除 OAuth state，避免回调重放。"""
        result = self._client.eval(CONSUME_OAUTH_STATE_SCRIPT, 1, self._oauth_state_key(state))
        return result.decode() if isinstance(result, bytes) else result

    def _code_key(self, key_type: str, account: str, purpose: str) -> str:
        account_digest = hashlib.sha256(account.encode("utf-8")).hexdigest()
        return f"{self._key_prefix}:{key_type}:{purpose}:{account_digest}"

    def _session_key(self, token_digest: str) -> str:
        return f"{self._key_prefix}:session:{token_digest}"

    def _oauth_state_key(self, state: str) -> str:
        return f"{self._key_prefix}:oauth-state:{state}"
