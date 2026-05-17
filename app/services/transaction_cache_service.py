import json

from app.db.redis import get_redis

MONTHLY_STATS_TTL_SECONDS = 60 * 5  # 5 minutes


def monthly_stats_key(
    uid: str,
    year: int,
    month: int,
    payment_method_id: int | None = None,
) -> str:
    payment_key = payment_method_id if payment_method_id is not None else "all"
    return f"monthly_stats:{uid}:{year}:{month}:payment:{payment_key}"


def monthly_stats_pattern(uid: str, year: int, month: int) -> str:
    return f"monthly_stats:{uid}:{year}:{month}:payment:*"


async def get_cached_monthly_stats(
    uid: str,
    year: int,
    month: int,
    payment_method_id: int | None = None,
) -> dict | None:
    redis = await get_redis()

    raw = await redis.get(
        monthly_stats_key(uid, year, month, payment_method_id)
    )

    if raw is None:
        return None

    return json.loads(raw)


async def set_cached_monthly_stats(
    uid: str,
    year: int,
    month: int,
    stats: dict,
    payment_method_id: int | None = None,
):
    redis = await get_redis()

    await redis.set(
        monthly_stats_key(uid, year, month, payment_method_id),
        json.dumps(stats, ensure_ascii=False),
        ex=MONTHLY_STATS_TTL_SECONDS,
    )


async def invalidate_monthly_stats_cache(
    uid: str,
    year: int,
    month: int,
):
    """
    Deletes all cached versions for that user/month:
    - all payment methods
    - payment method 1
    - payment method 2
    - etc.
    """
    redis = await get_redis()
    pattern = monthly_stats_pattern(uid, year, month)

    keys_to_delete: list[str] = []

    async for key in redis.scan_iter(match=pattern):
        keys_to_delete.append(key)

    if keys_to_delete:
        await redis.delete(*keys_to_delete)