from fastapi import Depends, HTTPException, Request

from app.services.line_service import get_http_client
from app.services.token_cache_service import (
    check_rate_limit,
    get_cached_uid,
    set_cached_uid,
)

LINE_PROFILE_URL = "https://api.line.me/v2/profile"


async def get_current_uid(request: Request) -> str:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token")

    access_token = auth.removeprefix("Bearer ")

    uid = await get_cached_uid(access_token)

    if uid is None:
        resp = await get_http_client().get(
            LINE_PROFILE_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=5.0,
        )
        if resp.status_code != 200:
            raise HTTPException(status_code=401, detail="Invalid LINE access token")
        uid = resp.json()["userId"]
        await set_cached_uid(access_token, uid)

    await check_rate_limit(uid)

    return uid