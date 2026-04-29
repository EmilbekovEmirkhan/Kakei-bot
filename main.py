import hashlib
import hmac
import base64
import os
import traceback

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from receipt_parser import parse_receipt_bytes, format_receipt_reply
from contextlib import asynccontextmanager

load_dotenv()

CHANNEL_ACCESS_TOKEN = os.environ.get("CHANNEL_ACCESS_TOKEN", "")
CHANNEL_SECRET = os.environ.get("CHANNEL_SECRET", "")

LINE_REPLY_URL = "https://api.line.me/v2/bot/message/reply"
LINE_CONTENT_URL = "https://api-data.line.me/v2/bot/message/{message_id}/content"

http_client: httpx.AsyncClient = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global http_client
    async with httpx.AsyncClient() as client:
        http_client = client
        yield

app = FastAPI(lifespan=lifespan)

def verify_signature(body: bytes, x_line_signature: str) -> bool:
    digest = hmac.new(CHANNEL_SECRET.encode(), body, hashlib.sha256).digest()
    return hmac.compare_digest(base64.b64encode(digest).decode(), x_line_signature)

@app.post("/webhook")
async def webhook(request: Request):
    body = await request.body()
    if not verify_signature(body, request.headers.get("X-Line-Signature", "")):
        raise HTTPException(status_code=400, detail="Invalid signature")

    for event in (await request.json()).get("events", []):
        await handle_event(event)

    return JSONResponse({"status": "ok"})

async def handle_event(event: dict):
    if event.get("type") != "message":
        return

    message = event.get("message", {})
    reply_token = event.get("replyToken")

    if message.get("type") == "image":
        await handle_image_message(reply_token, message["id"])
    elif message.get("type") == "text":
        await reply_message(reply_token, f"You said: {message['text']}")

async def handle_image_message(reply_token: str, message_id: str):
    try:
        image_bytes = await download_image_from_line(message_id)
        reply_text = format_receipt_reply(parse_receipt_bytes(image_bytes))
    except Exception as exc:
        traceback.print_exc()
        reply_text = "レシートの読み取りに失敗しました。"

    await reply_message(reply_token, reply_text)

async def download_image_from_line(message_id: str) -> bytes:
    url = LINE_CONTENT_URL.format(message_id=message_id)
    response = await http_client.get(url, headers={"Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}"})
    response.raise_for_status()
    return response.content

async def reply_message(reply_token: str, text: str):
    payload = {"replyToken": reply_token, "messages": [{"type": "text", "text": text}]}
    response = await http_client.post(
        LINE_REPLY_URL,
        headers={"Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}", "Content-Type": "application/json"},
        json=payload,
    )
    response.raise_for_status()
