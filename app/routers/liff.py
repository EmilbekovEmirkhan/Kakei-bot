from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse

from app.config import LIFF_ID
from app.repositories.transaction_repo import get_monthly_stats, delete_transaction
from app.services.line_service import get_http_client

router = APIRouter()

LINE_PROFILE_URL = "https://api.line.me/v2/profile"
_LIFF_HTML_CONTENT = (
    (Path(__file__).parent.parent / "static" / "liff" / "index.html")
    .read_text(encoding="utf-8")
    .replace("{{LIFF_ID}}", LIFF_ID)
)


async def _verify_line_token(access_token: str) -> str:
    resp = await get_http_client().get(
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
    try:
        year  = int(request.query_params.get("year",  now.year))
        month = int(request.query_params.get("month", now.month))
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid year/month")

    stats = await get_monthly_stats(uid, year, month)
    return JSONResponse(stats)


@router.delete("/api/transaction/{transaction_id}")
async def api_delete_transaction(transaction_id: int, request: Request):
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token")

    uid = await _verify_line_token(auth.removeprefix("Bearer "))
    deleted = await delete_transaction(uid, transaction_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return JSONResponse({"ok": True})


@router.get("/liff", response_class=HTMLResponse)
async def liff_page():
    return HTMLResponse(_LIFF_HTML_CONTENT)
