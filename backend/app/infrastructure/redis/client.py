from collections.abc import Generator

from redis import Redis

from app.core.config import get_settings


def create_redis_client() -> Redis:
    return Redis.from_url(get_settings().redis_url, decode_responses=True)


def get_redis_client() -> Generator[Redis, None, None]:
    client = create_redis_client()
    try:
        yield client
    finally:
        client.close()
