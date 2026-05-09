from datetime import datetime

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse

from app.repositories.transaction_repo import get_monthly_stats

router = APIRouter()

LINE_PROFILE_URL = "https://api.line.me/v2/profile"


async def _verify_line_token(access_token: str) -> str:
    """Verify LINE access token and return uid."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            LINE_PROFILE_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=5.0,
        )
    if resp.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid LINE access token")
    return resp.json()["userId"]


@router.get("/api/stats")
async def api_stats(request: Request):
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token")

    access_token = auth.removeprefix("Bearer ")
    uid = await _verify_line_token(access_token)

    now = datetime.now()
    # Support ?year=YYYY&month=MM query params for history browsing
    try:
        year  = int(request.query_params.get("year",  now.year))
        month = int(request.query_params.get("month", now.month))
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid year/month")

    stats = await get_monthly_stats(uid, year, month)
    return JSONResponse(stats)


@router.get("/liff", response_class=HTMLResponse)
async def liff_page():
    from app.config import LIFF_ID
    with open("app/static/liff/index.html", encoding="utf-8") as f:
        html = f.read().replace("{{LIFF_ID}}", LIFF_ID)
    return HTMLResponse(html)
