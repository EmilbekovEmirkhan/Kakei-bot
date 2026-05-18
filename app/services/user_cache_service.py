from app.db.redis import get_redis

USER_LANGUAGE_TTL_SECONDS = 60 * 60 * 24 * 90  # 90 days


def user_language_key(uid: str) -> str:
    return f"user:{uid}:language"


async def get_cached_user_language(uid: str) -> str | None:
    redis = await get_redis()
    lang = await redis.get(user_language_key(uid))

    if lang in ("ja", "en"):
        return lang

    return None


async def set_cached_user_language(uid: str, lang: str):
    if lang not in ("ja", "en"):
        lang = "ja"

    redis = await get_redis()
    await redis.set(
        user_language_key(uid),
        lang,
        ex=USER_LANGUAGE_TTL_SECONDS,
    )


async def delete_cached_user_language(uid: str):
    redis = await get_redis()
    await redis.delete(user_language_key(uid))