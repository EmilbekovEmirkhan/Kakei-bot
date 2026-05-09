from app.db.connection import get_pool


async def get_monthly_stats(uid: str, year: int, month: int) -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        total_row = await conn.fetchrow("""
            SELECT COALESCE(SUM(amount), 0) AS total, COUNT(*) AS count
            FROM transactions
            WHERE uid = $1
              AND EXTRACT(YEAR  FROM transacted_at) = $2
              AND EXTRACT(MONTH FROM transacted_at) = $3
        """, uid, year, month)

        category_rows = await conn.fetch("""
            SELECT
                c.name  AS category_name,
                c.icon  AS category_icon,
                COALESCE(SUM(t.amount), 0) AS subtotal,
                COUNT(*) AS count
            FROM transactions t
            LEFT JOIN categories c ON c.id = t.category_id
            WHERE t.uid = $1
              AND EXTRACT(YEAR  FROM t.transacted_at) = $2
              AND EXTRACT(MONTH FROM t.transacted_at) = $3
            GROUP BY c.id, c.name, c.icon
            ORDER BY subtotal DESC
        """, uid, year, month)

        return {
            "year":  year,
            "month": month,
            "total": int(total_row["total"]),
            "count": int(total_row["count"]),
            "by_category": [
                {
                    "name":     row["category_name"] or "その他",
                    "icon":     row["category_icon"] or "📦",
                    "subtotal": int(row["subtotal"]),
                    "count":    int(row["count"]),
                }
                for row in category_rows
            ],
        }


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
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            RETURNING id
        """, uid, amount, transacted_at, category_id, payment_method_id, receipt_image_url, note)
        return row["id"]