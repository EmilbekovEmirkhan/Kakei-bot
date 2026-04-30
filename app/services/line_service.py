import hashlib
import hmac
import base64
import traceback
from datetime import datetime

import httpx
from app.services.receipt_service import parse_receipt_bytes, format_receipt_reply
from app.repositories.user_repo import upsert_user
from app.repositories.transaction_repo import get_monthly_stats
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
    if event.get("type") != "message":
        return

    message     = event.get("message", {})
    reply_token = event.get("replyToken")
    user_id     = event.get("source", {}).get("userId")

    if user_id:
        try:
            profile = await get_line_profile(user_id)
            await upsert_user(
                uid=user_id,
                name=profile.get("displayName", ""),
                language_code=profile.get("language", ""),
            )
        except Exception:
            pass

    if message.get("type") == "image":
        await handle_image_message(reply_token, message["id"], user_id)
    elif message.get("type") == "text":
        text = message["text"].strip()
        if text == "統計":
            await handle_stats(reply_token, user_id)
        elif text == "使い方":
            await handle_how_to_use(reply_token)
        else:
            await reply_message(reply_token, f"You said: {message['text']}")


async def handle_image_message(reply_token: str, message_id: str, user_id: str):
    try:
        image_bytes = await download_image_from_line(message_id)
        parsed      = parse_receipt_bytes(image_bytes)
        reply_text  = format_receipt_reply(parsed)
    except Exception:
        traceback.print_exc()
        reply_text = "レシートの読み取りに失敗しました。"

    await reply_message(reply_token, reply_text)


async def handle_stats(reply_token: str, user_id: str | None):
    if not user_id:
        await reply_message(reply_token, "ユーザー情報が取得できませんでした。")
        return
    try:
        stats = await get_monthly_stats(user_id)
        if not stats:
            await reply_message(reply_token, "今月のデータがありません。")
            return

        total = sum(r["total"] for r in stats)
        month = datetime.today().strftime("%Y年%-m月")
        lines = [f"📊 {month}の統計\n"]
        for r in stats:
            pct = round(r["total"] / total * 100)
            lines.append(f"{r['icon']} {r['name']:<8} ¥{r['total']:,} ({pct}%)")
        lines.append(f"\n合計: ¥{total:,}")

        await reply_message(reply_token, "\n".join(lines))
    except Exception:
        traceback.print_exc()
        await reply_message(reply_token, "統計の取得に失敗しました。")


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