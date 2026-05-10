import asyncio
import json

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
from app.services.line_service import verify_signature, handle_event

router = APIRouter()

@router.post("/webhook")
async def webhook(request: Request):
    body = await request.body()
    if not verify_signature(body, request.headers.get("X-Line-Signature", "")):
        raise HTTPException(status_code=400, detail="Invalid signature")

    events = json.loads(body).get("events", [])
    if events:
        await asyncio.gather(*[handle_event(e) for e in events])

    return JSONResponse({"status": "ok"})