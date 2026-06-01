import hashlib

from app.db.redis import get_redis
from fastapi import HTTPException

TOKEN_TTL_SECONDS = 60 * 5   # 5 min - short since tokens can be revoked
RATE_LIMIT_WINDOW = 60       # seconds
RATE_LIMIT_MAX    = 30       # requests per window per uid


def _token_key(access_token: str) -> str:
    hashed = hashlib.sha256(access_token.encode()).hexdigest()
    return f"line_token:{hashed}"

def _rate_key(uid: str) -> str:
    return f"rate:{uid}"


async def get_cached_uid(access_token: str) -> str | None:
    redis = await get_redis()
    uid = await redis.get(_token_key(access_token))
    return uid if uid else None


async def set_cached_uid(access_token: str, uid: str) -> None:
    redis = await get_redis()
    await redis.set(_token_key(access_token), uid, ex=TOKEN_TTL_SECONDS)


async def check_rate_limit(uid: str) -> None:
    """Raises 429 if uid exceeds RATE_LIMIT_MAX requests per RATE_LIMIT_WINDOW."""
    redis  = await get_redis()
    key    = _rate_key(uid)
    count  = await redis.incr(key)
    if count == 1:
        await redis.expire(key, RATE_LIMIT_WINDOW)
    if count > RATE_LIMIT_MAX:
        raise HTTPException(status_code=429, detail="Too many requests")