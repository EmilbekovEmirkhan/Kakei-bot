from app.db.connection import get_pool


async def get_category_id_by_name(name: str) -> int | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT id FROM categories WHERE name = $1", name)
        return row["id"] if row else None