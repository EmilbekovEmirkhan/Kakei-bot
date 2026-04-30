from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
from app.services.line_service import verify_signature, handle_event

router = APIRouter()

@router.post("/webhook")
async def webhook(request: Request):
    body = await request.body()
    if not verify_signature(body, request.headers.get("X-Line-Signature", "")):
        raise HTTPException(status_code=400, detail="Invalid signature")

    for event in (await request.json()).get("events", []):
        await handle_event(event)

    return JSONResponse({"status": "ok"})