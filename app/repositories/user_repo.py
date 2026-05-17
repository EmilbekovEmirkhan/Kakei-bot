from app.db.connection import get_pool
from app.services.user_cache_service import (
    get_cached_user_language,
    set_cached_user_language,
    delete_cached_user_language,
)


async def create_user(uid: str, name: str, language_code: str = ""):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO users (uid, name, language_code)
            VALUES ($1, $2, $3)
            ON CONFLICT (uid) DO UPDATE
            SET name       = $2,
                blocked_at = NULL
        """, uid, name, language_code)


async def get_user_language_from_db(uid: str) -> str:
    """Returns 'ja' or 'en'. Defaults to 'ja' if unset or user not found."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT language_code FROM users WHERE uid = $1", uid
        )
    if not row:
        return "ja"
    code = row["language_code"]
    return code if code in ("ja", "en") else "ja"

async def get_user_language(uid: str) -> str:
    """
    Cached language lookup.
    Redis is checked first.
    PostgreSQL is used as source of truth on cache miss.
    """
    cached_lang = await get_cached_user_language(uid)

    if cached_lang:
        return cached_lang

    lang = await get_user_language_from_db(uid)
    await set_cached_user_language(uid, lang)

    return lang


async def set_user_language(uid: str, lang: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET language_code = $1 WHERE uid = $2", lang, uid
        )

    await set_cached_user_language(uid, lang)

async def deactivate_user(uid: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET blocked_at = NOW() WHERE uid = $1", uid
        )
    await delete_cached_user_language(uid)