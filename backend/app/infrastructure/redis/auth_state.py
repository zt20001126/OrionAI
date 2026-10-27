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


@dataclass(frozen=True)
class AuthSession:
    account: str
    password_fingerprint: str


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
            }
        )
        self._client.setex(self._session_key(token_digest), ttl_seconds, payload)

    def get_session(self, token_digest: str) -> AuthSession | None:
        payload = self._client.get(self._session_key(token_digest))
        if payload is None:
            return None
        try:
            session_data = json.loads(payload)
            account = session_data["account"]
            password_fingerprint = session_data["password_fingerprint"]
            if not isinstance(account, str) or not isinstance(password_fingerprint, str):
                raise ValueError("Invalid session payload")
            return AuthSession(
                account=account,
                password_fingerprint=password_fingerprint,
            )
        except (KeyError, TypeError, ValueError):
            self.delete_session(token_digest)
            return None

    def delete_session(self, token_digest: str) -> None:
        self._client.delete(self._session_key(token_digest))

    def _code_key(self, key_type: str, account: str, purpose: str) -> str:
        account_digest = hashlib.sha256(account.encode("utf-8")).hexdigest()
        return f"{self._key_prefix}:{key_type}:{purpose}:{account_digest}"

    def _session_key(self, token_digest: str) -> str:
        return f"{self._key_prefix}:session:{token_digest}"
