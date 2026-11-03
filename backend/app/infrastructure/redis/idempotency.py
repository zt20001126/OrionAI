"""Redis 原子幂等状态存取适配器。"""

from collections.abc import Callable
from typing import Protocol, TypeVar

from redis import Redis
from redis.exceptions import RedisError

Result = TypeVar("Result")


class IdempotencyStoreError(Exception):
    """Redis 幂等存储不可用。"""


class IdempotencyStore(Protocol):
    """会话 Service 使用的幂等存储能力。"""

    def reserve(self, key: str, value: str, *, ttl_seconds: int) -> bool: ...

    def get(self, key: str) -> str | None: ...

    def set_if_token(self, key: str, token: str, value: str, *, ttl_seconds: int) -> bool: ...

    def set_if_state(
        self,
        key: str,
        state: str,
        request_hash: str,
        value: str,
        *,
        ttl_seconds: int,
    ) -> bool: ...

    def delete_if_token(self, key: str, token: str) -> bool: ...


class RedisIdempotencyStore:
    """将 SET NX 和带条件的状态转换封装在 Redis 基础设施层。"""

    _SET_IF_TOKEN_SCRIPT = """
local raw = redis.call('GET', KEYS[1])
if not raw then return 0 end
local current = cjson.decode(raw)
if current['token'] ~= ARGV[1] then return 0 end
redis.call('SET', KEYS[1], ARGV[2], 'EX', ARGV[3])
return 1
"""
    _SET_IF_STATE_SCRIPT = """
local raw = redis.call('GET', KEYS[1])
if not raw then return 0 end
local current = cjson.decode(raw)
if current['state'] ~= ARGV[1] or current['request_hash'] ~= ARGV[2] then return 0 end
redis.call('SET', KEYS[1], ARGV[3], 'EX', ARGV[4])
return 1
"""
    _DELETE_IF_TOKEN_SCRIPT = """
local raw = redis.call('GET', KEYS[1])
if not raw then return 0 end
local current = cjson.decode(raw)
if current['token'] ~= ARGV[1] then return 0 end
return redis.call('DEL', KEYS[1])
"""

    def __init__(self, client: Redis) -> None:
        self._client = client

    def reserve(self, key: str, value: str, *, ttl_seconds: int) -> bool:
        return self._run(lambda: bool(self._client.set(key, value, nx=True, ex=ttl_seconds)))

    def get(self, key: str) -> str | None:
        return self._run(lambda: self._client.get(key))

    def set_if_token(self, key: str, token: str, value: str, *, ttl_seconds: int) -> bool:
        return self._run(
            lambda: bool(
                self._client.eval(
                    self._SET_IF_TOKEN_SCRIPT,
                    1,
                    key,
                    token,
                    value,
                    ttl_seconds,
                )
            )
        )

    def set_if_state(
        self,
        key: str,
        state: str,
        request_hash: str,
        value: str,
        *,
        ttl_seconds: int,
    ) -> bool:
        return self._run(
            lambda: bool(
                self._client.eval(
                    self._SET_IF_STATE_SCRIPT,
                    1,
                    key,
                    state,
                    request_hash,
                    value,
                    ttl_seconds,
                )
            )
        )

    def delete_if_token(self, key: str, token: str) -> bool:
        return self._run(
            lambda: bool(self._client.eval(self._DELETE_IF_TOKEN_SCRIPT, 1, key, token))
        )

    @staticmethod
    def _run(operation: Callable[[], Result]) -> Result:
        try:
            return operation()
        except RedisError as error:
            raise IdempotencyStoreError from error
