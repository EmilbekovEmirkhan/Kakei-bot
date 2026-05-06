from app.db.connection import get_pool


async def save_transaction(
    uid: str,
    amount: int,
    transacted_at,
    category_id: int | None,
    payment_method_id: int | None,
    receipt_image_url: str | None = None,
    note: str | None = None,
) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            INSERT INTO transactions
                (uid, amount, transacted_at, category_id, payment_method_id, receipt_image_url, note)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            RETURNING id
        """, uid, amount, transacted_at, category_id, payment_method_id, receipt_image_url, note)
        return row["id"]