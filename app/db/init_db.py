import asyncpg
from pathlib import Path
from app.db.connection import get_pool

MIGRATIONS_DIR = Path(__file__).parent / "migrations"

SEED_CATEGORIES = [
    ("食費",        "🍱"),
    ("交通費",      "🚃"),
    ("日用品",      "🛒"),
    ("カフェ",      "☕"),
    ("外食",        "🍜"),
    ("ショッピング", "🛍️"),
    ("その他",      "📦"),
]

SEED_PAYMENT_METHODS = [
    ("現金",            "💴"),
    ("クレジットカード",  "💳"),
    ("電子マネー",       "📱"),
    ("QRコード",        "📲"),
    ("不明",            "❓"),
]


async def init_db():
    pool = await get_pool()
    sql = (MIGRATIONS_DIR / "init_tables.sql").read_text()

    async with pool.acquire() as conn:
        await conn.execute(sql)

        count = await conn.fetchval("SELECT COUNT(*) FROM categories")
        if count == 0:
            await conn.executemany(
                "INSERT INTO categories (name, icon) VALUES ($1, $2)",
                SEED_CATEGORIES,
            )

        count = await conn.fetchval("SELECT COUNT(*) FROM payment_methods")
        if count == 0:
            await conn.executemany(
                "INSERT INTO payment_methods (name, icon) VALUES ($1, $2)",
                SEED_PAYMENT_METHODS,
            )