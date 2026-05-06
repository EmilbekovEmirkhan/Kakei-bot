import hashlib
import hmac
import base64
import traceback
from datetime import datetime
from urllib.parse import urlencode, parse_qs

import httpx
from app.services.receipt_service import parse_receipt_bytes, format_receipt_reply
from app.repositories.user_repo import create_user, deactivate_user
from app.repositories.transaction_repo import save_transaction
from app.services.line_state_service import (
    set_manual_entry_state,
    get_manual_entry_state,
    delete_manual_entry_state,
)
from app.config import CHANNEL_SECRET, CHANNEL_ACCESS_TOKEN

CATEGORIES = [
    {"id": 1, "name": "食費", "icon": "🍱"},
    {"id": 2, "name": "交通費", "icon": "🚃"},
    {"id": 3, "name": "日用品", "icon": "🛒"},
    {"id": 4, "name": "カフェ", "icon": "☕"},
    {"id": 5, "name": "外食", "icon": "🍜"},
    {"id": 6, "name": "ショッピング", "icon": "🛍️"},
    {"id": 7, "name": "その他", "icon": "📦"},
]

PAYMENT_METHODS = [
    {"id": 1, "name": "現金", "icon": "💴"},
    {"id": 2, "name": "クレジットカード", "icon": "💳"},
    {"id": 3, "name": "電子マネー", "icon": "📱"},
    {"id": 4, "name": "QRコード", "icon": "📲"},
    {"id": 5, "name": "不明", "icon": "❓"},
]

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

    if event_type == "postback":
        await handle_postback(event)
        return

    if event_type == "message":
        await handle_message(event)
        return
    
async def handle_message(event: dict):
    message     = event.get("message", {})
    reply_token = event.get("replyToken")
    user_id     = event.get("source", {}).get("userId")

    if not reply_token or not user_id:
        return

    message_type = message.get("type")

    if message_type == "image":
        await handle_image_message(reply_token, message["id"], user_id)
        return

    if message_type == "text":
        await handle_text_message(reply_token, user_id, message)
        return
    
async def handle_text_message(reply_token: str, user_id: str, message: dict):
    text = message.get("text", "").strip()

    if text == "使い方":
        await handle_how_to_use(reply_token)
        return

    if text == "手動で入力":
        await start_manual_entry(reply_token, user_id)
        return

    manual_state = await get_manual_entry_state(user_id)
    if manual_state:
        await handle_manual_text_input(reply_token, user_id, text, manual_state)
        return

    await reply_message(reply_token, f"You said: {text}")

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

async def reply_raw_message(reply_token: str, messages: list[dict]):
    payload = {
        "replyToken": reply_token,
        "messages": messages,
    }

    response = await _http_client.post(
        LINE_REPLY_URL,
        headers={
            "Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}",
            "Content-Type": "application/json",
        },
        json=payload,
    )
    response.raise_for_status()

def make_manual_postback_data(step: str, **kwargs) -> str:
    payload = {
        "flow": "manual",
        "step": step,
        **kwargs,
    }
    return urlencode(payload)


def parse_postback_data(data: str) -> dict:
    parsed = parse_qs(data)
    return {key: values[0] for key, values in parsed.items()}


def quick_reply_postback_item(
    label: str,
    data: str,
    input_option: str | None = None,
    fill_in_text: str | None = None,
) -> dict:
    action = {
        "type": "postback",
        "label": label,
        "data": data,
        "displayText": label,
    }

    if input_option:
        action["inputOption"] = input_option

    if fill_in_text:
        action["fillInText"] = fill_in_text

    return {
        "type": "action",
        "action": action,
    }

async def start_manual_entry(reply_token: str, user_id: str):
    await set_manual_entry_state(user_id, {
        "step": "date",
    })

    message = {
        "type": "text",
        "text": "日付を選択してください / Please choose a date",
        "quickReply": {
            "items": [
                {
                    "type": "action",
                    "action": {
                        "type": "datetimepicker",
                        "label": "日付を選ぶ",
                        "data": make_manual_postback_data("date"),
                        "mode": "date",
                    }
                }
            ]
        }
    }

    await reply_raw_message(reply_token, [message])

async def handle_postback(event: dict):
    reply_token = event.get("replyToken")
    user_id = event.get("source", {}).get("userId")

    if not reply_token or not user_id:
        return

    postback = event.get("postback", {})
    data = parse_postback_data(postback.get("data", ""))

    if data.get("flow") != "manual":
        return

    step = data.get("step")

    if step == "date":
        selected_date = postback.get("params", {}).get("date")

        if not selected_date:
            await reply_message(reply_token, "日付を取得できませんでした。もう一度お試しください。")
            return

        await set_manual_entry_state(user_id, {
            "step": "category",
            "date": selected_date,
        })

        await ask_category(reply_token, selected_date)
        return

    if step == "category":
        state = await get_manual_entry_state(user_id)

        if not state:
            await reply_message(reply_token, "入力セッションが期限切れです。「手動で入力」からもう一度始めてください。")
            return

        category_id = int(data["category_id"])
        category = find_category(category_id)

        if not category:
            await reply_message(reply_token, "カテゴリを取得できませんでした。もう一度お試しください。")
            return

        state.update({
            "step": "payment",
            "category_id": category_id,
            "category_name": category["name"],
            "category_icon": category["icon"],
        })

        await set_manual_entry_state(user_id, state)
        await ask_payment_method(reply_token, state)
        return

    if step == "payment":
        state = await get_manual_entry_state(user_id)

        if not state:
            await reply_message(reply_token, "入力セッションが期限切れです。「手動で入力」からもう一度始めてください。")
            return

        payment_method_id = int(data["payment_method_id"])
        payment = find_payment_method(payment_method_id)

        if not payment:
            await reply_message(reply_token, "支払方法を取得できませんでした。もう一度お試しください。")
            return

        state.update({
            "step": "amount",
            "payment_method_id": payment_method_id,
            "payment_method_name": payment["name"],
            "payment_method_icon": payment["icon"],
        })

        await set_manual_entry_state(user_id, state)

        text = (
            "金額を入力してください / Please enter the amount\n\n"
            f"日付: {state['date']}\n"
            f"カテゴリ: {state['category_icon']} {state['category_name']}\n"
            f"支払方法: {state['payment_method_icon']} {state['payment_method_name']}\n\n"
            "例: 1200"
        )

        await reply_message(reply_token, text)
        return
    if step == "note_skip":
        state = await get_manual_entry_state(user_id)

        if not state:
            await reply_message(reply_token, "入力セッションが期限切れです。「手動で入力」からもう一度始めてください。")
            return

        await save_manual_transaction(reply_token, user_id, state, note=None)
        return

    if step == "note_add":
        state = await get_manual_entry_state(user_id)

        if not state:
            await reply_message(reply_token, "入力セッションが期限切れです。「手動で入力」からもう一度始めてください。")
            return

        state["step"] = "note"
        await set_manual_entry_state(user_id, state)

        await reply_message(
            reply_token,
            "メモを入力してください / Please enter a note"
        )
        return
    
async def save_manual_transaction(
    reply_token: str,
    user_id: str,
    state: dict,
    note: str | None,
):
    try:
        transacted_at = datetime.strptime(state["date"], "%Y-%m-%d")

        transaction_id = await save_transaction(
            uid=user_id,
            amount=state["amount"],
            transacted_at=transacted_at,
            category_id=state["category_id"],
            payment_method_id=state["payment_method_id"],
            receipt_image_url=None,
            note=note,
        )

        await delete_manual_entry_state(user_id)

        reply_text = (
            "✅ 登録しました / Transaction saved\n\n"
            f"ID: {transaction_id}\n"
            f"日付: {state['date']}\n"
            f"カテゴリ: {state['category_icon']} {state['category_name']}\n"
            f"支払方法: {state['payment_method_icon']} {state['payment_method_name']}\n"
            f"金額: ¥{state['amount']:,}\n"
            f"メモ: {note or 'なし'}"
        )

        await reply_message(reply_token, reply_text)

    except Exception:
        traceback.print_exc()
        await reply_message(reply_token, "保存に失敗しました。もう一度お試しください。")
    
async def ask_category(reply_token: str, selected_date: str):
    items = []

    for category in CATEGORIES:
        label = f"{category['icon']} {category['name']}"

        data = make_manual_postback_data(
            "category",
            category_id=str(category["id"]),
        )

        items.append(quick_reply_postback_item(label, data))

    message = {
        "type": "text",
        "text": (
            "カテゴリを選択してください / Please choose a category\n\n"
            f"日付: {selected_date}"
        ),
        "quickReply": {
            "items": items
        }
    }

    await reply_raw_message(reply_token, [message])

def find_category(category_id: int) -> dict | None:
    for category in CATEGORIES:
        if category["id"] == category_id:
            return category
    return None

async def ask_payment_method(reply_token: str, state: dict):
    items = []

    for payment in PAYMENT_METHODS:
        label = f"{payment['icon']} {payment['name']}"

        data = make_manual_postback_data(
            "payment",
            payment_method_id=str(payment["id"]),
        )

        items.append(
            quick_reply_postback_item(
                label,
                data,
                input_option="openKeyboard",
            )
        )

    message = {
        "type": "text",
        "text": (
            "支払方法を選択してください / Please choose payment method\n\n"
            f"日付: {state['date']}\n"
            f"カテゴリ: {state['category_icon']} {state['category_name']}"
        ),
        "quickReply": {
            "items": items
        }
    }

    await reply_raw_message(reply_token, [message])

def find_payment_method(payment_method_id: int) -> dict | None:
    for payment in PAYMENT_METHODS:
        if payment["id"] == payment_method_id:
            return payment
    return None

async def ask_note_option(reply_token: str):
    message = {
        "type": "text",
        "text": (
            "メモを追加しますか？ / Would you like to add a note?"
        ),
        "quickReply": {
            "items": [
                quick_reply_postback_item(
                    label="スキップ",
                    data=make_manual_postback_data("note_skip"),
                ),
                quick_reply_postback_item(
                    label="メモを追加",
                    data=make_manual_postback_data("note_add"),
                    input_option="openKeyboard",
                ),
            ]
        }
    }

    await reply_raw_message(reply_token, [message])

async def handle_manual_text_input(
    reply_token: str,
    user_id: str,
    text: str,
    state: dict,
):
    step = state.get("step")

    if step == "amount":
        amount_text = (
            text
            .replace(",", "")
            .replace("円", "")
            .replace("¥", "")
            .strip()
        )

        if not amount_text.isdigit():
            await reply_message(reply_token, "金額は数字で入力してください。\n例: 1200")
            return

        state["amount"] = int(amount_text)
        state["step"] = "note"

        await set_manual_entry_state(user_id, state)

        await ask_note_option(reply_token)
        return

    if step == "note":
        note = text.strip()

        if not note:
            await reply_message(reply_token, "メモを入力するか、「スキップ」を選択してください。")
            return

        await save_manual_transaction(reply_token, user_id, state, note=note)
        return

    await reply_message(reply_token, "入力状態が正しくありません。「手動で入力」からもう一度始めてください。")
    await delete_manual_entry_state(user_id)