import hashlib
import hmac
import base64
import traceback
from datetime import datetime
from urllib.parse import urlencode, parse_qs

import httpx
from app.services.receipt_service import parse_receipt_bytes
from app.repositories.user_repo import create_user, deactivate_user
from app.repositories.transaction_repo import save_transaction
from app.services.line_state_service import (
    set_manual_entry_state,
    get_manual_entry_state,
    delete_manual_entry_state,
)
from app.config import CHANNEL_SECRET, CHANNEL_ACCESS_TOKEN
from app.constants import CATEGORIES, PAYMENT_METHODS

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


def get_http_client() -> httpx.AsyncClient:
    if _http_client is None:
        raise RuntimeError("HTTP client not initialized")
    return _http_client


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

    state = await get_manual_entry_state(user_id)
    if state:
        if state.get("flow") == "receipt":
            await handle_receipt_text_input(reply_token, user_id, text, state)
        else:
            await handle_manual_text_input(reply_token, user_id, text, state)
        return

    await reply_message(reply_token, f"You said: {text}")

async def handle_follow(event: dict):
    user_id = event.get("source", {}).get("userId")
    if not user_id:
        return
    try:
        profile = await get_line_profile(user_id)
    except Exception:
        traceback.print_exc()
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
        parsed = parse_receipt_bytes(image_bytes)
    except Exception:
        traceback.print_exc()
        await reply_message(reply_token, "レシートの読み取りに失敗しました。")
        return

    scanned_date = parsed.get("date")
    scanned_amount = parsed.get("amount")
    scanned_category_id = parsed.get("category_id")
    scanned_payment_id = parsed.get("payment_method_id")

    store_name = parsed.get("store_name", "不明")

    category = find_category(scanned_category_id) if scanned_category_id else None
    payment = find_payment_method(scanned_payment_id) if scanned_payment_id else None

    state = {
        "flow": "receipt",
        "step": "review",
        "store_name": store_name,
        "date": scanned_date,
        "amount": scanned_amount,
        "category_id": category["id"] if category else None,
        "category_name": category["name"] if category else None,
        "category_icon": category["icon"] if category else None,
        "payment_method_id": payment["id"] if payment else None,
        "payment_method_name": payment["name"] if payment else None,
        "payment_method_icon": payment["icon"] if payment else None,
        "note": None,
    }

    await set_manual_entry_state(user_id, state)
    await ask_receipt_review(reply_token, state)
    
async def handle_how_to_use(reply_token: str):
    text = (
        "📖 使い方 / How to use\n\n"
        "1️⃣ レシートの写真を送ってください\n"
        "   → ボットが自動で読み取ります\n\n"
        "2️⃣ 内容を確認してください\n"
        "   店名・カテゴリ・金額・支払方法\n\n"
        "3️⃣ 統計はメニューの「マイプロフィール」から確認できます\n"
        "   → 今月の支出をカテゴリ別に表示します\n\n"
        "ご不明な点はお気軽にどうぞ！"
    )
    await reply_message(reply_token, text)


async def download_image_from_line(message_id: str) -> bytes:
    url = LINE_CONTENT_URL.format(message_id=message_id)
    response = await _http_client.get(url, headers={"Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}"}, timeout=10.0)
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
        "flow": "manual",
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
                },
                get_cancel_item(),
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
    flow = data.get("flow")

    if flow == "cancel":
        await delete_manual_entry_state(user_id)
        await reply_message(reply_token, "キャンセルしました / Cancelled ✅")
        return

    if flow == "manual":
        await handle_manual_postback(reply_token, user_id, data, postback)
    elif flow == "receipt":
        await handle_receipt_postback(reply_token, user_id, data, postback)


async def handle_manual_postback(reply_token: str, user_id: str, data: dict, postback: dict):
    step = data.get("step")

    if step == "date":
        selected_date = postback.get("params", {}).get("date")
        if not selected_date:
            await reply_message(reply_token, "日付を取得できませんでした。もう一度お試しください。")
            return
        await set_manual_entry_state(user_id, {"flow": "manual", "step": "category", "date": selected_date})
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
        state.update({"step": "payment", "category_id": category_id, "category_name": category["name"], "category_icon": category["icon"]})
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
        state.update({"step": "amount", "payment_method_id": payment_method_id, "payment_method_name": payment["name"], "payment_method_icon": payment["icon"]})
        await set_manual_entry_state(user_id, state)
        await reply_raw_message(reply_token, [{
                                                "type": "text",
                                                "text": (
                                                    "金額を入力してください / Please enter the amount\n\n"
                                                    f"日付: {state['date']}\n"
                                                    f"カテゴリ: {state['category_icon']} {state['category_name']}\n"
                                                    f"支払方法: {state['payment_method_icon']} {state['payment_method_name']}\n\n"
                                                    "例: 1200"
                                                ),
                                                "quickReply": {
                                                    "items": [get_cancel_item()]  # ← here
                                                }
                                            }])
        return

    if step == "note_skip":
        state = await get_manual_entry_state(user_id)
        if not state:
            await reply_message(reply_token, "入力セッションが期限切れです。「手動で入力」からもう一度始めてください。")
            return
        state["note"] = None
        state["step"] = "confirm"
        await set_manual_entry_state(user_id, state)
        await ask_confirm(reply_token, state)
        return

    if step == "note_add":
        state = await get_manual_entry_state(user_id)
        if not state:
            await reply_message(reply_token, "入力セッションが期限切れです。「手動で入力」からもう一度始めてください。")
            return
        state["step"] = "note"
        await set_manual_entry_state(user_id, state)
        await reply_message(reply_token, "メモを入力してください / Please enter a note")
        return

    if step == "confirm":
        state = await get_manual_entry_state(user_id)
        if not state:
            await reply_message(reply_token, "入力セッションが期限切れです。「手動で入力」からもう一度始めてください。")
            return
        await save_transaction_from_state(reply_token, user_id, state)
        return

    if step == "restart":
        await delete_manual_entry_state(user_id)
        await start_manual_entry(reply_token, user_id)
        return
    
def make_receipt_postback_data(step: str, **kwargs) -> str:
    payload = {"flow": "receipt", "step": step, **kwargs}
    return urlencode(payload)


async def handle_receipt_postback(reply_token: str, user_id: str, data: dict, postback: dict):
    step = data.get("step")
    state = await get_manual_entry_state(user_id)

    if not state or state.get("flow") != "receipt":
        await reply_message(reply_token, "セッションが期限切れです。もう一度レシートを送ってください。")
        return

    if step == "confirm_all":
        await save_transaction_from_state(reply_token, user_id, state)
        return

    if step == "edit":
        state["step"] = "edit_date"
        await set_manual_entry_state(user_id, state)
        await ask_receipt_date(reply_token, state)
        return

    if step == "date_confirm":
        state["step"] = "edit_category"
        await set_manual_entry_state(user_id, state)
        await ask_receipt_category(reply_token, state)
        return

    if step == "date_pick":
        selected_date = postback.get("params", {}).get("date")
        if not selected_date:
            await reply_message(reply_token, "日付を取得できませんでした。もう一度お試しください。")
            return
        state["date"] = selected_date
        state["step"] = "edit_category"
        await set_manual_entry_state(user_id, state)
        await ask_receipt_category(reply_token, state)
        return

    if step == "category_confirm":
        state["step"] = "edit_payment"
        await set_manual_entry_state(user_id, state)
        await ask_receipt_payment(reply_token, state)
        return

    if step == "category_pick":
        category_id = int(data["category_id"])
        category = find_category(category_id)
        if not category:
            await reply_message(reply_token, "カテゴリを取得できませんでした。")
            return
        state.update({"category_id": category["id"], "category_name": category["name"], "category_icon": category["icon"], "step": "edit_payment"})
        await set_manual_entry_state(user_id, state)
        await ask_receipt_payment(reply_token, state)
        return

    if step == "payment_confirm":
        state["step"] = "edit_amount"
        await set_manual_entry_state(user_id, state)
        await ask_receipt_amount(reply_token, state)
        return

    if step == "payment_pick":
        payment_id = int(data["payment_method_id"])
        payment = find_payment_method(payment_id)
        if not payment:
            await reply_message(reply_token, "支払方法を取得できませんでした。")
            return
        state.update({"payment_method_id": payment["id"], "payment_method_name": payment["name"], "payment_method_icon": payment["icon"], "step": "edit_amount"})
        await set_manual_entry_state(user_id, state)
        await ask_receipt_amount(reply_token, state)
        return

    if step == "amount_confirm":
        state["step"] = "edit_note"
        await set_manual_entry_state(user_id, state)
        await ask_receipt_note_option(reply_token)
        return

    if step == "amount_edit":
        state["step"] = "edit_amount_input"
        await set_manual_entry_state(user_id, state)
        await reply_message(reply_token, "金額を入力してください / Please enter the amount\n\n例: 1200")
        return

    if step == "note_skip":
        state["note"] = None
        state["step"] = "edit_confirm"
        await set_manual_entry_state(user_id, state)
        await ask_receipt_final_confirm(reply_token, state)
        return

    if step == "note_add":
        state["step"] = "edit_note_input"
        await set_manual_entry_state(user_id, state)
        await reply_message(reply_token, "メモを入力してください / Please enter a note")
        return

    if step == "final_confirm":
        await save_transaction_from_state(reply_token, user_id, state)
        return

    if step == "restart":
        await delete_manual_entry_state(user_id)
        await reply_message(reply_token, "最初からやり直します。レシートをもう一度送ってください。")
        return
    
async def ask_receipt_review(reply_token: str, state: dict):
    date_display = state.get("date") or "不明"
    amount_display = f"¥{state['amount']:,}" if state.get("amount") is not None else "不明"
    category_display = f"{state['category_icon']} {state['category_name']}" if state.get("category_name") else "不明"
    payment_display = f"{state['payment_method_icon']} {state['payment_method_name']}" if state.get("payment_method_name") else "不明"

    message = {
        "type": "text",
        "text": (
            f"🧾 {state.get('store_name', '不明')}\n\n"
            f"日付: {date_display}\n"
            f"カテゴリ: {category_display}\n"
            f"支払方法: {payment_display}\n"
            f"金額: {amount_display}\n\n"
            "内容を確認してください / Please review your receipt"
        ),
        "quickReply": {
            "items": [
                quick_reply_postback_item("✅ 確認", make_receipt_postback_data("confirm_all")),
                quick_reply_postback_item("✏️ 編集", make_receipt_postback_data("edit")),
                get_cancel_item(),
            ]
        },
    }
    await reply_raw_message(reply_token, [message])


async def ask_receipt_date(reply_token: str, state: dict):
    current_date = state.get("date")
    items = []

    if current_date:
        items.append(quick_reply_postback_item(f"✅ {current_date}", make_receipt_postback_data("date_confirm")))

    items.append({
        "type": "action",
        "action": {
            "type": "datetimepicker",
            "label": "📅 別の日付",
            "data": make_receipt_postback_data("date_pick"),
            "mode": "date",
        },
    })
    items.append(get_cancel_item())

    message = {
        "type": "text",
        "text": f"日付を確認してください / Confirm the date\n\nスキャン結果: {current_date or '不明'}",
        "quickReply": {"items": items},
    }
    await reply_raw_message(reply_token, [message])


async def ask_receipt_category(reply_token: str, state: dict):
    current_id = state.get("category_id")
    items = []

    if current_id:
        items.append(quick_reply_postback_item(
            f"✅ {state['category_icon']} {state['category_name']}",
            make_receipt_postback_data("category_confirm"),
        ))

    for category in CATEGORIES:
        if category["id"] == current_id:
            continue
        items.append(quick_reply_postback_item(
            f"{category['icon']} {category['name']}",
            make_receipt_postback_data("category_pick", category_id=str(category["id"])),
        ))
    items.append(get_cancel_item())

    message = {
        "type": "text",
        "text": (
            "カテゴリを確認してください / Confirm the category\n\n"
            f"スキャン結果: {state.get('category_icon', '')} {state.get('category_name', '不明')}"
        ),
        "quickReply": {"items": items},
    }
    await reply_raw_message(reply_token, [message])


async def ask_receipt_payment(reply_token: str, state: dict):
    current_id = state.get("payment_method_id")
    items = []

    if current_id:
        items.append(quick_reply_postback_item(
            f"✅ {state['payment_method_icon']} {state['payment_method_name']}",
            make_receipt_postback_data("payment_confirm"),
        ))

    for payment in PAYMENT_METHODS:
        if payment["id"] == current_id:
            continue
        items.append(quick_reply_postback_item(
            f"{payment['icon']} {payment['name']}",
            make_receipt_postback_data("payment_pick", payment_method_id=str(payment["id"])),
        ))
    items.append(get_cancel_item())

    message = {
        "type": "text",
        "text": (
            "支払方法を確認してください / Confirm payment method\n\n"
            f"スキャン結果: {state.get('payment_method_icon', '')} {state.get('payment_method_name', '不明')}"
        ),
        "quickReply": {"items": items},
    }
    await reply_raw_message(reply_token, [message])


async def ask_receipt_amount(reply_token: str, state: dict):
    current_amount = state.get("amount")
    items = []

    if current_amount is not None:
        items.append(quick_reply_postback_item(
            f"✅ ¥{current_amount:,}",
            make_receipt_postback_data("amount_confirm"),
        ))

    items.append(quick_reply_postback_item(
        "✏️ 手動で入力",
        make_receipt_postback_data("amount_edit"),
        input_option="openKeyboard",
    ))
    
    items.append(get_cancel_item())

    message = {
        "type": "text",
        "text": (
            "金額を確認してください / Confirm the amount\n\n"
            f"スキャン結果: {f'¥{current_amount:,}' if current_amount is not None else '不明'}"
        ),
        "quickReply": {"items": items},
    }
    await reply_raw_message(reply_token, [message])


async def ask_receipt_note_option(reply_token: str):
    message = {
        "type": "text",
        "text": "メモを追加しますか？ / Would you like to add a note?",
        "quickReply": {
            "items": [
                quick_reply_postback_item("スキップ", make_receipt_postback_data("note_skip")),
                quick_reply_postback_item("メモを追加", make_receipt_postback_data("note_add"), input_option="openKeyboard"),
                get_cancel_item(),
            ]
        },
    }
    await reply_raw_message(reply_token, [message])


async def ask_receipt_final_confirm(reply_token: str, state: dict):
    note_display = state.get("note") or "なし"
    amount_display = f"¥{state['amount']:,}" if state.get("amount") is not None else "不明"
    message = {
        "type": "text",
        "text": (
            "以下の内容で登録しますか？ / Confirm your entry:\n\n"
            f"日付: {state.get('date', '不明')}\n"
            f"カテゴリ: {state.get('category_icon', '')} {state.get('category_name', '不明')}\n"
            f"支払方法: {state.get('payment_method_icon', '')} {state.get('payment_method_name', '不明')}\n"
            f"金額: {amount_display}\n"
            f"メモ: {note_display}"
        ),
        "quickReply": {
            "items": [
                quick_reply_postback_item("✅ 確認", make_receipt_postback_data("final_confirm")),
                quick_reply_postback_item("🔄 やり直す", make_receipt_postback_data("restart")),
                get_cancel_item(),
            ]
        },
    }
    await reply_raw_message(reply_token, [message])

async def handle_receipt_text_input(reply_token: str, user_id: str, text: str, state: dict):
    if text in ("キャンセル", "cancel"):
        await delete_manual_entry_state(user_id)
        await reply_message(reply_token, "キャンセルしました / Cancelled ✅")
        return

    step = state.get("step")

    if step == "edit_amount_input":
        amount_text = text.replace(",", "").replace("円", "").replace("¥", "").strip()
        if not amount_text.isdigit():
            await reply_message(reply_token, "金額は数字で入力してください。\n例: 1200")
            return
        state["amount"] = int(amount_text)
        state["step"] = "edit_note"
        await set_manual_entry_state(user_id, state)
        await ask_receipt_note_option(reply_token)
        return

    if step == "edit_note_input":
        note = text.strip()
        if not note:
            await reply_message(reply_token, "メモを入力するか、「スキップ」を選択してください。")
            return
        state["note"] = note
        state["step"] = "edit_confirm"
        await set_manual_entry_state(user_id, state)
        await ask_receipt_final_confirm(reply_token, state)
        return

    await reply_message(reply_token, "操作が正しくありません。レシートをもう一度送ってください。")
    await delete_manual_entry_state(user_id)

async def save_transaction_from_state(reply_token: str, user_id: str, state: dict):
    try:
        date_str = state.get("date")
        transacted_at = datetime.strptime(date_str, "%Y-%m-%d") if date_str else datetime.now()
        note = state.get("note")

        transaction_id = await save_transaction(
            uid=user_id,
            amount=state["amount"],
            transacted_at=transacted_at,
            category_id=state.get("category_id"),
            payment_method_id=state.get("payment_method_id"),
            receipt_image_url=None,
            note=note,
        )

        await delete_manual_entry_state(user_id)

        amount_display = f"¥{state['amount']:,}" if state.get("amount") is not None else "不明"
        reply_text = (
            "✅ 登録しました / Transaction saved\n\n"
            f"日付: {state.get('date', '不明')}\n"
            f"カテゴリ: {state.get('category_icon', '')} {state.get('category_name', '不明')}\n"
            f"支払方法: {state.get('payment_method_icon', '')} {state.get('payment_method_name', '不明')}\n"
            f"金額: {amount_display}\n"
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
    items.append(get_cancel_item())

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

        items.append(quick_reply_postback_item(label, data, input_option="openKeyboard"))
    
    items.append(get_cancel_item())

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
                get_cancel_item(),
            ]
        }
    }

    await reply_raw_message(reply_token, [message])

async def ask_confirm(reply_token: str, state: dict):
    note_display = state.get("note") or "なし"
    message = {
        "type": "text",
        "text": (
            "以下の内容で登録しますか？ / Confirm your entry:\n\n"
            f"日付: {state['date']}\n"
            f"カテゴリ: {state['category_icon']} {state['category_name']}\n"
            f"支払方法: {state['payment_method_icon']} {state['payment_method_name']}\n"
            f"金額: ¥{state['amount']:,}\n"
            f"メモ: {note_display}"
        ),
        "quickReply": {
            "items": [
                quick_reply_postback_item(
                    label="✅ 確認",
                    data=make_manual_postback_data("confirm"),
                ),
                quick_reply_postback_item(
                    label="🔄 やり直す",
                    data=make_manual_postback_data("restart"),
                ),
                get_cancel_item(),
            ]
        },
    }
    await reply_raw_message(reply_token, [message])

async def handle_manual_text_input(
    reply_token: str,
    user_id: str,
    text: str,
    state: dict,
):
    if text in ("キャンセル", "cancel"):
        await delete_manual_entry_state(user_id)
        await reply_message(reply_token, "キャンセルしました / Cancelled ✅")
        return

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

        state["note"] = note
        state["step"] = "confirm"
        await set_manual_entry_state(user_id, state)
        await ask_confirm(reply_token, state)
        return

    await reply_message(reply_token, "入力状態が正しくありません。「手動で入力」からもう一度始めてください。")
    await delete_manual_entry_state(user_id)

def get_cancel_item() -> dict:
    return quick_reply_postback_item(
        "❌ キャンセル",
        urlencode({"flow": "cancel"}),
    )