from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse

from app.config import LIFF_ID
from app.constants import CATEGORIES, PAYMENT_METHODS
from app.dependencies import get_current_uid
from app.repositories.transaction_repo import delete_transaction, get_monthly_stats
from app.repositories.user_repo import get_user_language

router = APIRouter()

_LIFF_HTML_CONTENT = (
    (Path(__file__).parent.parent / "static" / "liff" / "index.html")
    .read_text(encoding="utf-8")
    .replace("{{LIFF_ID}}", LIFF_ID)
)

_CAT_JA_TO_EN  = {c["name"]: c.get("name_en", c["name"]) for c in CATEGORIES}
_PAY_LABEL_MAP = {
    f"{p['icon']} {p['name']}": f"{p['icon']} {p['name_en']}"
    for p in PAYMENT_METHODS
}


def _localise_stats(stats: dict, lang: str) -> None:
    if lang != "en":
        return
    for cat in stats.get("by_category", []):
        cat["name"] = _CAT_JA_TO_EN.get(cat["name"], cat["name"])
        for txn in cat.get("transactions", []):
            txn["payment"] = _PAY_LABEL_MAP.get(txn["payment"], txn["payment"])


@router.get("/api/stats")
async def api_stats(request: Request, uid: str = Depends(get_current_uid)):
    now = datetime.now()
    try:
        year              = int(request.query_params.get("year",  now.year))
        month             = int(request.query_params.get("month", now.month))
        payment_method_id = int(p) if (p := request.query_params.get("payment_method_id")) else None
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid query params")

    if not (2000 <= year <= now.year + 1):
        raise HTTPException(status_code=400, detail="Invalid year")
    if not (1 <= month <= 12):
        raise HTTPException(status_code=400, detail="Invalid month")

    lang  = await get_user_language(uid)
    stats = await get_monthly_stats(uid, year, month, payment_method_id)
    stats["lang"] = lang
    _localise_stats(stats, lang)
    return JSONResponse(stats)


@router.delete("/api/transaction/{transaction_id}")
async def api_delete_transaction(
    transaction_id: int,
    uid: str = Depends(get_current_uid),
):
    deleted = await delete_transaction(uid, transaction_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return JSONResponse({"ok": True})


@router.get("/liff", response_class=HTMLResponse)
async def liff_page():
    return HTMLResponse(_LIFF_HTML_CONTENT)
