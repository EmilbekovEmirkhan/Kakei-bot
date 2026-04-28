import hashlib
import hmac
import base64
import httpx
import os

from dotenv import load_dotenv

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from google.cloud import vision

# ── Config ────────────────────────────────────────────────────────────────────
load_dotenv()
CHANNEL_ACCESS_TOKEN = os.getenv("CHANNEL_ACCESS_TOKEN") 
CHANNEL_SECRET = os.getenv("CHANNEL_SECRET") 

LINE_REPLY_URL = "https://api.line.me/v2/bot/reply"
LINE_CONTENT_URL = "https://api-data.line.me/v2/bot/message/{message_id}/content"

# ── Clients ───────────────────────────────────────────────────────────────────

vision_client = vision.ImageAnnotatorClient.from_service_account_file("credentials.json")

app = FastAPI()

# ── Signature verification ────────────────────────────────────────────────────

def verify_signature(body: bytes, x_line_signature: str) -> bool:
    hash_value = hmac.new(
        CHANNEL_SECRET.encode("utf-8"), body, hashlib.sha256
    ).digest()
    expected = base64.b64encode(hash_value).decode("utf-8")
    return hmac.compare_digest(expected, x_line_signature)

# ── Webhook endpoint ──────────────────────────────────────────────────────────

@app.post("/webhook")
async def webhook(request: Request):
    body = await request.body()
    signature = request.headers.get("X-Line-Signature", "")

    if not verify_signature(body, signature):
        raise HTTPException(status_code=400, detail="Invalid signature")

    payload = await request.json()

    for event in payload.get("events", []):
        await handle_event(event)

    return JSONResponse({"status": "ok"})

# ── Event handlers ────────────────────────────────────────────────────────────

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
        extracted_text = extract_text_from_image(image_bytes)

        reply_text = (
            f"📝 Extracted text:\n\n{extracted_text}"
            if extracted_text
            else "No text found in the image."
        )
    except Exception as exc:
        print(f"Image processing error: {exc}")
        reply_text = "Sorry, failed to process the image."

    await reply_message(reply_token, reply_text)

# ── LINE helpers ──────────────────────────────────────────────────────────────

async def download_image_from_line(message_id: str) -> bytes:
    url = LINE_CONTENT_URL.format(message_id=message_id)
    headers = {"Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}"}
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        return response.content

async def reply_message(reply_token: str, text: str):
    headers = {
        "Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "replyToken": reply_token,
        "messages": [{"type": "text", "text": text}],
    }
    async with httpx.AsyncClient() as client:
        response = await client.post(LINE_REPLY_URL, headers=headers, json=payload)
        response.raise_for_status()

# ── Google Vision helper ──────────────────────────────────────────────────────

def extract_text_from_image(image_bytes: bytes) -> str | None:
    image = vision.Image(content=image_bytes)
    response = vision_client.text_detection(image=image)
    annotations = response.text_annotations
    if not annotations:
        return None
    return annotations[0].description