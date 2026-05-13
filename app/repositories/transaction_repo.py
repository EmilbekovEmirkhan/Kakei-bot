from collections import defaultdict

from app.db.connection import get_pool


async def get_monthly_stats(
    uid: str,
    year: int,
    month: int,
    payment_method_id: int | None = None,
) -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
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
              AND ($4::int IS NULL OR t.payment_method_id = $4)
            GROUP BY c.id, c.name, c.icon
            ORDER BY subtotal DESC
        """, uid, year, month, payment_method_id)

        txn_rows = await conn.fetch("""
            SELECT
                t.id,
                t.amount,
                t.note,
                t.transacted_at,
                c.name  AS category_name,
                c.icon  AS category_icon,
                p.name  AS payment_name,
                p.icon  AS payment_icon
            FROM transactions t
            LEFT JOIN categories      c ON c.id = t.category_id
            LEFT JOIN payment_methods p ON p.id = t.payment_method_id
            WHERE t.uid = $1
              AND EXTRACT(YEAR  FROM t.transacted_at) = $2
              AND EXTRACT(MONTH FROM t.transacted_at) = $3
              AND ($4::int IS NULL OR t.payment_method_id = $4)
            ORDER BY t.transacted_at DESC
        """, uid, year, month, payment_method_id)

        total = sum(int(r["subtotal"]) for r in category_rows)
        count = sum(int(r["count"]) for r in category_rows)

        txns_by_cat: dict[str, list] = defaultdict(list)
        for t in txn_rows:
            cat = t["category_name"] or "その他"
            txns_by_cat[cat].append({
                "id":      t["id"],
                "amount":  int(t["amount"]),
                "note":    t["note"] or "",
                "date":    t["transacted_at"].strftime("%Y-%m-%d"),
                "payment": (t["payment_icon"] or "") + " " + (t["payment_name"] or ""),
            })

        return {
            "year":  year,
            "month": month,
            "total": total,
            "count": count,
            "by_category": [
                {
                    "name":         row["category_name"] or "その他",
                    "icon":         row["category_icon"] or "📦",
                    "subtotal":     int(row["subtotal"]),
                    "count":        int(row["count"]),
                    "transactions": txns_by_cat[row["category_name"] or "その他"],
                }
                for row in category_rows
                if int(row["subtotal"]) > 0
            ],
        }


async def delete_transaction(uid: str, transaction_id: int) -> bool:
    """Delete a transaction. Returns True if deleted, False if not found or not owned by uid."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM transactions WHERE id = $1 AND uid = $2",
            transaction_id, uid,
        )
        return result == "DELETE 1"


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