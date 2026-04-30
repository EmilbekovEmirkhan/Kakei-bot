from app.db.connection import get_pool


async def create_user(uid: str, name: str, language_code: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO users (uid, name, language_code)
            VALUES ($1, $2, $3)
            ON CONFLICT (uid) DO UPDATE
            SET name          = $2,
                language_code = $3,
                blocked_at    = NULL
        """, uid, name, language_code)


async def deactivate_user(uid: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE users SET blocked_at = NOW() WHERE uid = $1
        """, uid)