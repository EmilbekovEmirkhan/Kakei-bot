from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse

from app.config import LIFF_ID
from app.constants import CATEGORIES, PAYMENT_METHODS
from app.repositories.transaction_repo import get_monthly_stats, delete_transaction
from app.repositories.user_repo import get_user_language
from app.services.line_service import get_http_client

router = APIRouter()

LINE_PROFILE_URL = "https://api.line.me/v2/profile"
_LIFF_HTML_CONTENT = (
    (Path(__file__).parent.parent / "static" / "liff" / "index.html")
    .read_text(encoding="utf-8")
    .replace("{{LIFF_ID}}", LIFF_ID)
)

# Pre-built translation maps (built once at startup)
_CAT_JA_TO_EN  = {c["name"]: c.get("name_en", c["name"]) for c in CATEGORIES}
_PAY_LABEL_MAP = {
    f"{p['icon']} {p['name']}": f"{p['icon']} {p['name_en']}"
    for p in PAYMENT_METHODS
}


def _localise_stats(stats: dict, lang: str) -> None:
    """Translate category names and payment labels in-place when lang == 'en'."""
    if lang != "en":
        return
    for cat in stats.get("by_category", []):
        cat["name"] = _CAT_JA_TO_EN.get(cat["name"], cat["name"])
        for txn in cat.get("transactions", []):
            txn["payment"] = _PAY_LABEL_MAP.get(txn["payment"], txn["payment"])


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
        year              = int(request.query_params.get("year",  now.year))
        month             = int(request.query_params.get("month", now.month))
        payment_method_id = int(p) if (p := request.query_params.get("payment_method_id")) else None
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid query params")

    lang  = await get_user_language(uid)
    stats = await get_monthly_stats(uid, year, month, payment_method_id)
    stats["lang"] = lang
    _localise_stats(stats, lang)
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
