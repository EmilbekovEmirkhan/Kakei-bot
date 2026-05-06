import hashlib
import hmac
import base64
import traceback
from datetime import datetime

import httpx
from app.services.receipt_service import parse_receipt_bytes, format_receipt_reply
from app.repositories.user_repo import create_user, deactivate_user
from app.config import CHANNEL_SECRET, CHANNEL_ACCESS_TOKEN

LINE_REPLY_URL   = "https://api.line.me/v2/bot/message/reply"
LINE_CONTENT_URL = "https://api-data.line.me/v2/bot/message/{message_id}/content"

_http_client: httpx.AsyncClient | None = None


async def init_http_client():
    global _http_client
    _http_client = httpx.AsyncClient()


async def close_http_client():
    global _http_client
    if _http_client:
        await _http_client.aclose()
        _http_client = None


def verify_signature(body: bytes, x_line_signature: str) -> bool:
    digest = hmac.new(CHANNEL_SECRET.encode(), body, hashlib.sha256).digest()
    return hmac.compare_digest(base64.b64encode(digest).decode(), x_line_signature)


async def get_line_profile(user_id: str) -> dict:
    url = f"https://api.line.me/v2/bot/profile/{user_id}"
    response = await _http_client.get(url, headers={"Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}"})
    response.raise_for_status()
    return response.json()


async def handle_event(event: dict):
    event_type = event.get("type")

    if event_type == "follow":
        await handle_follow(event)
        return

    if event_type == "unfollow":
        await handle_unfollow(event)
        return

    if event_type != "message":
        return

    message     = event.get("message", {})
    reply_token = event.get("replyToken")
    user_id     = event.get("source", {}).get("userId")

    if message.get("type") == "image":
        await handle_image_message(reply_token, message["id"], user_id)
    elif message.get("type") == "text":
        text = message["text"].strip()
        if text == "使い方":
            await handle_how_to_use(reply_token)
        else:
            await reply_message(reply_token, f"You said: {message['text']}")


async def handle_follow(event: dict):
    user_id = event.get("source", {}).get("userId")
    if not user_id:
        return
    try:
        profile = await get_line_profile(user_id)
    except Exception as e:
        return
    await create_user(
        uid=user_id,
        name=profile.get("displayName", ""),
        language_code=profile.get("language", ""),
    )


async def handle_unfollow(event: dict):
    user_id = event.get("source", {}).get("userId")
    if not user_id:
        return
    await deactivate_user(user_id)

async def handle_image_message(reply_token: str, message_id: str, user_id: str):
    try:
        image_bytes = await download_image_from_line(message_id)
        parsed      = parse_receipt_bytes(image_bytes)
        reply_text  = format_receipt_reply(parsed)
    except Exception:
        traceback.print_exc()
        reply_text = "レシートの読み取りに失敗しました。"

    await reply_message(reply_token, reply_text)

async def handle_how_to_use(reply_token: str):
    text = (
        "📖 使い方 / How to use\n\n"
        "1️⃣ レシートの写真を送ってください\n"
        "   → ボットが自動で読み取ります\n\n"
        "2️⃣ 内容を確認してください\n"
        "   店名・カテゴリ・金額・支払方法\n\n"
        "3️⃣ 統計を見るには「統計」と送ってください\n"
        "   → 今月の支出をカテゴリ別に表示します\n\n"
        "ご不明な点はお気軽にどうぞ！"
    )
    await reply_message(reply_token, text)


async def download_image_from_line(message_id: str) -> bytes:
    url = LINE_CONTENT_URL.format(message_id=message_id)
    response = await _http_client.get(url, headers={"Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}"})
    response.raise_for_status()
    return response.content


async def reply_message(reply_token: str, text: str):
    payload = {
        "replyToken": reply_token,
        "messages": [{"type": "text", "text": text}]
    }
    response = await _http_client.post(
        LINE_REPLY_URL,
        headers={
            "Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}",
            "Content-Type": "application/json"
        },
        json=payload,
    )
    response.raise_for_status()