import hashlib
import hmac
import base64
import os
import traceback

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from datetime import datetime
from receipt_parser import parse_receipt_bytes, format_receipt_reply
from database import (
    init_db, close_pool,
    upsert_user,
    save_transaction,
    get_category_id_by_name,
    get_payment_method_id_by_name,
    get_or_create_place,
    get_monthly_stats,
)

load_dotenv()

CHANNEL_ACCESS_TOKEN = os.environ.get("CHANNEL_ACCESS_TOKEN", "")
CHANNEL_SECRET = os.environ.get("CHANNEL_SECRET", "")

LINE_REPLY_URL = "https://api.line.me/v2/bot/message/reply"
LINE_CONTENT_URL = "https://api-data.line.me/v2/bot/message/{message_id}/content"

http_client: httpx.AsyncClient = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global http_client
    await init_db()
    async with httpx.AsyncClient() as client:
        http_client = client
        yield
    await close_pool()

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

async def get_line_profile(user_id: str) -> dict:
    url = f"https://api.line.me/v2/bot/profile/{user_id}"
    response = await http_client.get(url, headers={"Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}"})
    response.raise_for_status()
    return response.json()


async def handle_event(event: dict):
    if event.get("type") != "message":
        return

    message = event.get("message", {})
    reply_token = event.get("replyToken")
    user_id = event.get("source", {}).get("userId")

    if user_id:
        try:
            profile = await get_line_profile(user_id)
            await upsert_user(
                line_user_id=user_id,
                display_name=profile.get("displayName", ""),
                picture_url=profile.get("pictureUrl", ""),
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
        parsed = parse_receipt_bytes(image_bytes)

        if user_id:
            category_id = await get_category_id_by_name(parsed.get("category"))
            payment_id = await get_payment_method_id_by_name(parsed.get("payment_method"))
            place_id = await get_or_create_place(parsed.get("store_name"), category_id) if parsed.get("store_name") else None
            amount = parsed.get("amount") or 0
            tax_amount = parsed.get("tax_amount")
            total_amount = parsed.get("total_amount") or amount

            await save_transaction(
                user_id=user_id,
                date=parsed.get("date") or datetime.today().strftime("%Y-%m-%d"),
                amount=amount,
                tax_amount=tax_amount,
                total_amount=total_amount,
                category_id=category_id,
                place_id=place_id,
                payment_method_id=payment_id,
            )

        reply_text = format_receipt_reply(parsed)
    except Exception as exc:
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
