from app.db.connection import get_pool


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


async def get_user_language(uid: str) -> str:
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


async def set_user_language(uid: str, lang: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET language_code = $1 WHERE uid = $2", lang, uid
        )


async def deactivate_user(uid: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET blocked_at = NOW() WHERE uid = $1", uid
        )