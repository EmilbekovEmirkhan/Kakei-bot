import ssl
import asyncpg
from app.config import DATABASE_URL

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        _pool = await asyncpg.create_pool(DATABASE_URL, ssl=ctx)
    return _pool


async def close_pool():
    global _pool
    if _pool:
        await _pool.close()
        _pool = None