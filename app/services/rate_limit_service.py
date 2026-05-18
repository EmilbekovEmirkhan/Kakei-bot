from app.db.redis import get_redis


def rate_limit_key(uid: str, scope: str) -> str:
    return f"rate_limit:{scope}:{uid}"


def temp_block_key(uid: str, scope: str) -> str:
    return f"temp_block:{scope}:{uid}"


def warning_key(uid: str, scope: str) -> str:
    return f"rate_limit_warning:{scope}:{uid}"


def lock_key(uid: str, lock_name: str) -> str:
    return f"lock:{lock_name}:{uid}"


async def is_temporarily_blocked(uid: str, scope: str) -> bool:
    redis = await get_redis()
    return await redis.exists(temp_block_key(uid, scope)) == 1


async def temporarily_block_user(
    uid: str,
    scope: str,
    ttl_seconds: int,
):
    redis = await get_redis()
    await redis.set(
        temp_block_key(uid, scope),
        "1",
        ex=ttl_seconds,
    )


async def should_send_warning(
    uid: str,
    scope: str,
    cooldown_seconds: int,
) -> bool:
    """
    Returns True only once during the cooldown window.
    Repeated spam during cooldown receives no reply.
    """
    redis = await get_redis()

    was_set = await redis.set(
        warning_key(uid, scope),
        "1",
        ex=cooldown_seconds,
        nx=True,
    )

    return bool(was_set)


async def is_rate_limited(
    uid: str,
    scope: str,
    limit: int,
    window_seconds: int,
) -> bool:
    """
    Fixed-window rate limiter.

    Returns True if the request should be blocked.
    Returns False if the request is allowed.
    """
    redis = await get_redis()

    key = rate_limit_key(uid, scope)
    current = await redis.incr(key)

    if current == 1:
        await redis.expire(key, window_seconds)

    return current > limit


async def acquire_user_lock(
    uid: str,
    lock_name: str,
    ttl_seconds: int,
) -> bool:
    """
    Returns True if lock was acquired.
    Returns False if lock already exists.
    """
    redis = await get_redis()

    return bool(await redis.set(
        lock_key(uid, lock_name),
        "1",
        ex=ttl_seconds,
        nx=True,
    ))


async def release_user_lock(uid: str, lock_name: str):
    redis = await get_redis()
    await redis.delete(lock_key(uid, lock_name))