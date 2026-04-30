from app.db.connection import get_pool


async def upsert_user(uid: str, name: str, language_code: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO users (uid, name, language_code)
            VALUES ($1, $2, $3)
            ON CONFLICT (uid) DO UPDATE
            SET name          = $2,
                language_code = $3
        """, uid, name, language_code)