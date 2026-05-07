import redis.asyncio as redis
from app.config import REDIS_URL

_redis_client: redis.Redis | None = None


async def init_redis():
    global _redis_client

    _redis_client = redis.from_url(
        REDIS_URL,
        encoding="utf-8",
        decode_responses=True,
    )

    await _redis_client.ping()


async def close_redis():
    global _redis_client

    if _redis_client:
        await _redis_client.aclose()
        _redis_client = None


async def get_redis() -> redis.Redis:
    if _redis_client is None:
        raise RuntimeError("Redis client is not initialized")

    return _redis_client