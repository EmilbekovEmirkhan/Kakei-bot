import json
from app.db.redis import get_redis

MANUAL_ENTRY_TTL_SECONDS = 15 * 60


def manual_entry_key(uid: str) -> str:
    return f"manual_entry:{uid}"


async def set_manual_entry_state(uid: str, state: dict):
    redis = await get_redis()
    await redis.set(
        manual_entry_key(uid),
        json.dumps(state, ensure_ascii=False),
        ex=MANUAL_ENTRY_TTL_SECONDS,
    )


async def get_manual_entry_state(uid: str) -> dict | None:
    redis = await get_redis()
    raw = await redis.get(manual_entry_key(uid))

    if raw is None:
        return None

    return json.loads(raw)


async def delete_manual_entry_state(uid: str):
    redis = await get_redis()
    await redis.delete(manual_entry_key(uid))