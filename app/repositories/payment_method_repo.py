from app.db.connection import get_pool


async def get_payment_method_id_by_name(name: str) -> int | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT id FROM payment_methods WHERE name = $1", name)
        return row["id"] if row else None