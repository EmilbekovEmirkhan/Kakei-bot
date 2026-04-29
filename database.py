"""
Database — PostgreSQL via asyncpg
Handles connection pool, table creation, and seed data.
"""

import os
from datetime import date as date_type
import asyncpg

DATABASE_URL = os.environ.get("DATABASE_URL", "")

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(DATABASE_URL)
    return _pool


async def close_pool():
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


# ── Table creation ────────────────────────────────────────────────────────────

CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS users (
    line_user_id    TEXT PRIMARY KEY,
    display_name    TEXT,
    picture_url     TEXT,
    language_code   TEXT,
    is_active       BOOLEAN DEFAULT true,
    is_blocked      BOOLEAN DEFAULT false,
    last_seen_at    TIMESTAMP,
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS categories (
    id      SERIAL PRIMARY KEY,
    name    TEXT NOT NULL,
    icon    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS payment_methods (
    id      SERIAL PRIMARY KEY,
    name    TEXT NOT NULL,
    icon    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS places (
    id           SERIAL PRIMARY KEY,
    name         TEXT NOT NULL,
    category_id  INTEGER REFERENCES categories(id)
);

CREATE TABLE IF NOT EXISTS transactions (
    id                  SERIAL PRIMARY KEY,
    user_id             TEXT NOT NULL REFERENCES users(line_user_id),
    date                DATE NOT NULL,
    amount              INTEGER NOT NULL,
    tax_amount          INTEGER,
    total_amount        INTEGER NOT NULL,
    category_id         INTEGER REFERENCES categories(id),
    place_id            INTEGER REFERENCES places(id),
    payment_method_id   INTEGER REFERENCES payment_methods(id),
    note                TEXT,
    created_at          TIMESTAMP DEFAULT NOW()
);
"""

# ── Seed data ─────────────────────────────────────────────────────────────────

SEED_CATEGORIES = [
    ("食費",       "🍱"),
    ("交通費",     "🚃"),
    ("日用品",     "🛒"),
    ("カフェ",     "☕"),
    ("外食",       "🍜"),
    ("ショッピング", "🛍️"),
    ("その他",     "📦"),
]

SEED_PAYMENT_METHODS = [
    ("現金",           "💴"),
    ("クレジットカード", "💳"),
    ("電子マネー",      "📱"),
    ("QRコード",       "📲"),
    ("不明",           "❓"),
]


async def init_db():
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(CREATE_TABLES_SQL)

        # Seed categories (only if empty)
        count = await conn.fetchval("SELECT COUNT(*) FROM categories")
        if count == 0:
            await conn.executemany(
                "INSERT INTO categories (name, icon) VALUES ($1, $2)",
                SEED_CATEGORIES,
            )

        # Seed payment_methods (only if empty)
        count = await conn.fetchval("SELECT COUNT(*) FROM payment_methods")
        if count == 0:
            await conn.executemany(
                "INSERT INTO payment_methods (name, icon) VALUES ($1, $2)",
                SEED_PAYMENT_METHODS,
            )


# ── User helpers ──────────────────────────────────────────────────────────────

async def upsert_user(line_user_id: str, display_name: str, picture_url: str, language_code: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO users (line_user_id, display_name, picture_url, language_code, last_seen_at)
            VALUES ($1, $2, $3, $4, NOW())
            ON CONFLICT (line_user_id) DO UPDATE
            SET display_name = $2,
                picture_url  = $3,
                language_code = $4,
                last_seen_at = NOW(),
                updated_at   = NOW()
        """, line_user_id, display_name, picture_url, language_code)


# ── Transaction helpers ───────────────────────────────────────────────────────

async def save_transaction(
    user_id: str,
    date: str,
    amount: int,
    tax_amount: int | None,
    total_amount: int,
    category_id: int | None,
    place_id: int | None,
    payment_method_id: int | None,
    note: str | None = None,
) -> int:
    if isinstance(date, str):
        date = date_type.fromisoformat(date)
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            INSERT INTO transactions
                (user_id, date, amount, tax_amount, total_amount, category_id, place_id, payment_method_id, note)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            RETURNING id
        """, user_id, date, amount, tax_amount, total_amount, category_id, place_id, payment_method_id, note)
        return row["id"]


async def get_monthly_stats(user_id: str) -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT c.name, c.icon, SUM(t.total_amount) AS total
            FROM transactions t
            JOIN categories c ON t.category_id = c.id
            WHERE t.user_id = $1
              AND DATE_TRUNC('month', t.date) = DATE_TRUNC('month', CURRENT_DATE)
            GROUP BY c.name, c.icon
            ORDER BY total DESC
        """, user_id)
        return [dict(r) for r in rows]


# ── Category/payment lookup ───────────────────────────────────────────────────

async def get_category_id_by_name(name: str) -> int | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT id FROM categories WHERE name = $1", name)
        return row["id"] if row else None


async def get_payment_method_id_by_name(name: str) -> int | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT id FROM payment_methods WHERE name = $1", name)
        return row["id"] if row else None


async def get_or_create_place(name: str, category_id: int | None) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT id FROM places WHERE name = $1", name)
        if row:
            return row["id"]
        row = await conn.fetchrow(
            "INSERT INTO places (name, category_id) VALUES ($1, $2) RETURNING id",
            name, category_id,
        )
        return row["id"]
