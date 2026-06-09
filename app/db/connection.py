import asyncpg
from app.config import DATABASE_URL

_pool: asyncpg.Pool | None = None

async def init_pool():
    global _pool
    _pool = await asyncpg.create_pool(DATABASE_URL, ssl="require")

async def close_pool():
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None

async def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Database pool is not initialized")
    return _pool