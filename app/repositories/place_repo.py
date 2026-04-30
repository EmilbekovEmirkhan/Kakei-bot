from app.db.connection import get_pool


async def get_or_create_place(uid: str, name: str, category_id: int | None) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id FROM places WHERE name = $1 AND uid = $2", name, uid
        )
        if row:
            return row["id"]
        row = await conn.fetchrow(
            "INSERT INTO places (name, category_id, uid) VALUES ($1, $2, $3) RETURNING id",
            name, category_id, uid,
        )
        return row["id"]