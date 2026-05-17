import hashlib
import hmac
import base64
import traceback
from datetime import datetime
from urllib.parse import urlencode, parse_qs

import httpx

from app.config import CHANNEL_SECRET, CHANNEL_ACCESS_TOKEN
from app.constants import CATEGORIES, PAYMENT_METHODS
from app.i18n import t
from app.repositories.user_repo import (
    create_user,
    deactivate_user,
    get_user_language,
    set_user_language,
)
from app.repositories.transaction_repo import save_transaction
from app.services.line_state_service import (
    delete_manual_entry_state,
    get_manual_entry_state,
    set_manual_entry_state,
)
from app.services.receipt_service import parse_receipt_image_async
from app.services.rate_limit_service import (
    is_rate_limited,
    is_temporarily_blocked,
    temporarily_block_user,
    should_send_warning,
    acquire_user_lock,
    release_user_lock,
)
LINE_REPLY_URL   = "https://api.line.me/v2/bot/message/reply"
LINE_PUSH_URL    = "https://api.line.me/v2/bot/message/push"
LINE_CONTENT_URL = "https://api-data.line.me/v2/bot/message/{message_id}/content"

TEXT_LIMIT = 30
TEXT_WINDOW_SECONDS = 60
TEXT_BLOCK_SECONDS = 60

IMAGE_LIMIT = 3
IMAGE_WINDOW_SECONDS = 60
IMAGE_BLOCK_SECONDS = 60

POSTBACK_LIMIT = 30
POSTBACK_WINDOW_SECONDS = 60
POSTBACK_BLOCK_SECONDS = 60

RECEIPT_PROCESSING_LOCK_SECONDS = 120

_http_client: httpx.AsyncClient | None = None


# ── HTTP client lifecycle ──────────────────────────────────────────────────

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


# ── Signature verification ─────────────────────────────────────────────────

def verify_signature(body: bytes, x_line_signature: str) -> bool:
    digest = hmac.new(CHANNEL_SECRET.encode(), body, hashlib.sha256).digest()
    return hmac.compare_digest(base64.b64encode(digest).decode(), x_line_signature)


# ── LINE API helpers ───────────────────────────────────────────────────────

async def get_line_profile(user_id: str) -> dict:
    url  = f"https://api.line.me/v2/bot/profile/{user_id}"
    resp = await _http_client.get(
        url, headers={"Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}"}
    )
    resp.raise_for_status()
    return resp.json()


async def reply_message(reply_token: str, text: str):
    await reply_raw_message(reply_token, [{"type": "text", "text": text}])


async def reply_raw_message(reply_token: str, messages: list[dict]):
    resp = await _http_client.post(
        LINE_REPLY_URL,
        headers={
            "Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}",
            "Content-Type": "application/json",
        },
        json={"replyToken": reply_token, "messages": messages},
    )
    resp.raise_for_status()


async def push_message(user_id: str, text: str):
    await push_raw_message(user_id, [{"type": "text", "text": text}])


async def push_raw_message(user_id: str, messages: list[dict]):
    resp = await _http_client.post(
        LINE_PUSH_URL,
        headers={
            "Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}",
            "Content-Type": "application/json",
        },
        json={"to": user_id, "messages": messages},
    )
    resp.raise_for_status()


async def download_image_from_line(message_id: str) -> bytes:
    url  = LINE_CONTENT_URL.format(message_id=message_id)
    resp = await _http_client.get(
        url,
        headers={"Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}"},
        timeout=10.0,
    )
    resp.raise_for_status()
    return resp.content


# ── Postback data helpers ──────────────────────────────────────────────────

def make_manual_postback_data(step: str, **kwargs) -> str:
    return urlencode({"flow": "manual", "step": step, **kwargs})


def make_receipt_postback_data(step: str, **kwargs) -> str:
    return urlencode({"flow": "receipt", "step": step, **kwargs})


def parse_postback_data(data: str) -> dict:
    parsed = parse_qs(data)
    return {k: v[0] for k, v in parsed.items()}


# ── Quick reply item builders ──────────────────────────────────────────────

def quick_reply_postback_item(
    label: str,
    data: str,
    input_option: str | None = None,
    fill_in_text: str | None = None,
) -> dict:
    action: dict = {
        "type":        "postback",
        "label":       label,
        "data":        data,
        "displayText": label,
    }
    if input_option:
        action["inputOption"] = input_option
    if fill_in_text:
        action["fillInText"] = fill_in_text
    return {"type": "action", "action": action}


def get_cancel_item(lang: str = "ja") -> dict:
    return quick_reply_postback_item(
        t("btn_cancel", lang), urlencode({"flow": "cancel"})
    )


def get_back_item(flow: str, to_step: str, lang: str = "ja") -> dict:
    make = make_manual_postback_data if flow == "manual" else make_receipt_postback_data
    return quick_reply_postback_item(t("btn_back", lang), make(f"back_{to_step}"))


# ── Lookup helpers ─────────────────────────────────────────────────────────

def find_category(category_id: int) -> dict | None:
    return next((c for c in CATEGORIES if c["id"] == category_id), None)


def find_payment_method(payment_method_id: int) -> dict | None:
    return next((p for p in PAYMENT_METHODS if p["id"] == payment_method_id), None)


def _cat_name(c: dict, lang: str) -> str:
    return c.get("name_en", c["name"]) if lang == "en" else c["name"]


def _pay_name(p: dict, lang: str) -> str:
    return p.get("name_en", p["name"]) if lang == "en" else p["name"]


# ── Top-level event router ─────────────────────────────────────────────────

async def handle_event(event: dict):
    event_type = event.get("type")
    if event_type == "follow":
        await handle_follow(event)
    elif event_type == "unfollow":
        await handle_unfollow(event)
    elif event_type == "postback":
        await handle_postback(event)
    elif event_type == "message":
        await handle_message(event)


# ── Follow / unfollow ──────────────────────────────────────────────────────

async def handle_follow(event: dict):
    user_id     = event.get("source", {}).get("userId")
    reply_token = event.get("replyToken")
    if not user_id:
        return
    try:
        profile = await get_line_profile(user_id)
        name    = profile.get("displayName", "")
        lang    = profile.get("language", "")
    except Exception:
        traceback.print_exc()
        name = ""
        lang = "jp"
    await create_user(uid=user_id, name=name, language_code=lang)
    if reply_token:
        await ask_language(reply_token, welcome=True)


async def handle_unfollow(event: dict):
    user_id = event.get("source", {}).get("userId")
    if user_id:
        await deactivate_user(user_id)


# ── Message routing ────────────────────────────────────────────────────────

async def handle_message(event: dict):
    message     = event.get("message", {})
    reply_token = event.get("replyToken")
    user_id     = event.get("source", {}).get("userId")

    if not reply_token or not user_id:
        return

    message_type = message.get("type")
    lang = await get_user_language(user_id)

    if message_type == "image":
        scope = "image"

        if await is_temporarily_blocked(user_id, scope):
            return

        limited = await is_rate_limited(
            uid=user_id,
            scope=scope,
            limit=IMAGE_LIMIT,
            window_seconds=IMAGE_WINDOW_SECONDS,
        )

        if limited:
            await temporarily_block_user(
                uid=user_id,
                scope=scope,
                ttl_seconds=IMAGE_BLOCK_SECONDS,
            )

            if await should_send_warning(
                uid=user_id,
                scope=scope,
                cooldown_seconds=IMAGE_BLOCK_SECONDS,
            ):
                await reply_message(reply_token, t("rate_limited_image", lang))

            return

        await handle_image_message(reply_token, message["id"], user_id, lang)
        return

    if message_type == "text":
        scope = "text"

        if await is_temporarily_blocked(user_id, scope):
            return

        limited = await is_rate_limited(
            uid=user_id,
            scope=scope,
            limit=TEXT_LIMIT,
            window_seconds=TEXT_WINDOW_SECONDS,
        )

        if limited:
            await temporarily_block_user(
                uid=user_id,
                scope=scope,
                ttl_seconds=TEXT_BLOCK_SECONDS,
            )

            if await should_send_warning(
                uid=user_id,
                scope=scope,
                cooldown_seconds=TEXT_BLOCK_SECONDS,
            ):
                await reply_message(reply_token, t("rate_limited_text", lang))

            return

        await handle_text_message(reply_token, user_id, message, lang)
        return

async def handle_text_message(reply_token: str, user_id: str, message: dict, lang: str):
    text  = message.get("text", "").strip()
    lower = text.lower()

    if text == "言語変更" or lower == "change language":
        await ask_language(reply_token)
        return

    if text == "使い方" or lower == "help":
        await reply_message(reply_token, t("how_to_use", lang))
        return

    if text == "手動で入力" or lower in ("manual entry", "manual"):
        await start_manual_entry(reply_token, user_id, lang)
        return

    state = await get_manual_entry_state(user_id)
    if state:
        if state.get("flow") == "receipt":
            await handle_receipt_text_input(reply_token, user_id, text, state, lang)
        else:
            await handle_manual_text_input(reply_token, user_id, text, state, lang)
        return

    await reply_message(reply_token, t("unknown_message", lang))


async def handle_image_message(reply_token: str, message_id: str, user_id: str, lang: str):
    lock_acquired = await acquire_user_lock(
        uid=user_id,
        lock_name="receipt_processing",
        ttl_seconds=RECEIPT_PROCESSING_LOCK_SECONDS,
    )

    if not lock_acquired:
        if await should_send_warning(
            uid=user_id,
            scope="receipt_processing",
            cooldown_seconds=60,
        ):
            await reply_message(reply_token, t("receipt_already_processing", lang))

        return

    await reply_message(reply_token, t("processing", lang))

    try:
        image_bytes = await download_image_from_line(message_id)
        parsed = await parse_receipt_image_async(image_bytes)

    except Exception:
        traceback.print_exc()
        await push_message(user_id, t("parse_failed", lang))
        return

    finally:
        await release_user_lock(user_id, "receipt_processing")

    scanned_cat_id     = parsed.get("category_id")
    scanned_payment_id = parsed.get("payment_method_id")
    category = find_category(scanned_cat_id) if scanned_cat_id else None
    payment  = find_payment_method(scanned_payment_id) if scanned_payment_id else None

    state = {
        "flow":                "receipt",
        "step":                "review",
        "lang":                lang,
        "store_name":          parsed.get("store_name", t("label_unknown", lang)),
        "date":                parsed.get("date"),
        "amount":              parsed.get("amount"),
        "category_id":         category["id"]              if category else None,
        "category_name":       _cat_name(category, lang)   if category else None,
        "category_icon":       category["icon"]            if category else None,
        "payment_method_id":   payment["id"]               if payment  else None,
        "payment_method_name": _pay_name(payment, lang)    if payment  else None,
        "payment_method_icon": payment["icon"]             if payment  else None,
        "note":                None,
    }
    await set_manual_entry_state(user_id, state)
    await push_receipt_review(user_id, state, lang)


# ── Language selection ─────────────────────────────────────────────────────

async def ask_language(reply_token: str, welcome: bool = False):
    messages = []
    if welcome:
        messages.append({
            "type": "text",
            "text": (
                "👋 こんにちは！ Welcome!\n\n"
                "家計 (Kakei) へようこそ！🏠\n"
                "レシートを写真で撮るだけで、自動で家計簿に記録できるLINEボットです 🧾✨\n\n"
                "Kakei is your personal LINE budget tracker - just snap a receipt and we log it automatically! ✨"
            ),
        })
    messages.append({
        "type": "text",
        "text": t("lang_select"),
        "quickReply": {
            "items": [
                quick_reply_postback_item(
                    t("lang_btn_ja"),
                    urlencode({"flow": "lang", "lang": "ja"}),
                ),
                quick_reply_postback_item(
                    t("lang_btn_en"),
                    urlencode({"flow": "lang", "lang": "en"}),
                ),
            ]
        },
    })
    await reply_raw_message(reply_token, messages)


# ── Postback routing ───────────────────────────────────────────────────────

async def handle_postback(event: dict):
    reply_token = event.get("replyToken")
    user_id     = event.get("source", {}).get("userId")
    if not reply_token or not user_id:
        return
    
    scope = "postback"

    if await is_temporarily_blocked(user_id, scope):
        return

    limited = await is_rate_limited(
        uid=user_id,
        scope=scope,
        limit=POSTBACK_LIMIT,
        window_seconds=POSTBACK_WINDOW_SECONDS,
    )

    if limited:
        await temporarily_block_user(
            uid=user_id,
            scope=scope,
            ttl_seconds=POSTBACK_BLOCK_SECONDS,
        )

        if await should_send_warning(
            uid=user_id,
            scope=scope,
            cooldown_seconds=POSTBACK_BLOCK_SECONDS,
        ):
            lang = await get_user_language(user_id)
            await reply_message(reply_token, t("rate_limited_text", lang))

        return

    postback = event.get("postback", {})
    data     = parse_postback_data(postback.get("data", ""))
    flow     = data.get("flow")

    if flow == "cancel":
        lang = await get_user_language(user_id)
        await delete_manual_entry_state(user_id)
        await reply_message(reply_token, t("cancelled", lang))
        return

    if flow == "lang":
        await handle_lang_postback(reply_token, user_id, data)
        return

    if flow == "manual":
        state = await get_manual_entry_state(user_id)
        lang  = state.get("lang") if state else await get_user_language(user_id)
        await handle_manual_postback(reply_token, user_id, data, postback, state, lang)
        return

    if flow == "receipt":
        state = await get_manual_entry_state(user_id)
        lang  = state.get("lang") if state else await get_user_language(user_id)
        await handle_receipt_postback(reply_token, user_id, data, postback, state, lang)
        return


async def handle_lang_postback(reply_token: str, user_id: str, data: dict):
    lang = data.get("lang", "ja")
    if lang not in ("ja", "en"):
        lang = "ja"
    await set_user_language(user_id, lang)
    key = "lang_saved_ja" if lang == "ja" else "lang_saved_en"
    await reply_raw_message(reply_token, [
        {"type": "text", "text": t(key, lang)},
        {"type": "text", "text": t("how_to_use", lang)},
    ])


# ── Manual entry flow ──────────────────────────────────────────────────────

async def start_manual_entry(reply_token: str, user_id: str, lang: str):
    await set_manual_entry_state(user_id, {"flow": "manual", "step": "date", "lang": lang})
    await ask_date(reply_token, lang)


async def ask_date(reply_token: str, lang: str):
    message = {
        "type": "text",
        "text": t("manual_ask_date", lang),
        "quickReply": {
            "items": [
                {
                    "type": "action",
                    "action": {
                        "type":  "datetimepicker",
                        "label": t("btn_select_date", lang),
                        "data":  make_manual_postback_data("date"),
                        "mode":  "date",
                    },
                },
                get_cancel_item(lang),
            ]
        },
    }
    await reply_raw_message(reply_token, [message])


async def ask_category(reply_token: str, date: str, lang: str):
    items = [
        quick_reply_postback_item(
            f"{c['icon']} {_cat_name(c, lang)}",
            make_manual_postback_data("category", category_id=str(c["id"])),
        )
        for c in CATEGORIES
    ]
    items.append(get_back_item("manual", "date", lang))
    items.append(get_cancel_item(lang))

    message = {
        "type": "text",
        "text": t("manual_ask_category", lang, date=date),
        "quickReply": {"items": items},
    }
    await reply_raw_message(reply_token, [message])


async def ask_payment_method(reply_token: str, state: dict, lang: str):
    items = [
        quick_reply_postback_item(
            f"{p['icon']} {_pay_name(p, lang)}",
            make_manual_postback_data("payment", payment_method_id=str(p["id"])),
            input_option="openKeyboard",
        )
        for p in PAYMENT_METHODS
    ]
    items.append(get_back_item("manual", "category", lang))
    items.append(get_cancel_item(lang))

    message = {
        "type": "text",
        "text": t(
            "manual_ask_payment", lang,
            date=state["date"],
            category=f"{state['category_icon']} {state['category_name']}",
        ),
        "quickReply": {"items": items},
    }
    await reply_raw_message(reply_token, [message])


async def ask_amount(reply_token: str, state: dict, lang: str):
    message = {
        "type": "text",
        "text": t(
            "manual_ask_amount", lang,
            date=state["date"],
            category=f"{state['category_icon']} {state['category_name']}",
            payment=f"{state['payment_method_icon']} {state['payment_method_name']}",
        ),
        "quickReply": {
            "items": [
                get_back_item("manual", "payment", lang),
                get_cancel_item(lang),
            ]
        },
    }
    await reply_raw_message(reply_token, [message])


async def ask_note_option(reply_token: str, lang: str, flow: str = "manual"):
    make_data = make_manual_postback_data if flow == "manual" else make_receipt_postback_data
    text_key  = "manual_ask_note" if flow == "manual" else "receipt_ask_note"
    message = {
        "type": "text",
        "text": t(text_key, lang),
        "quickReply": {
            "items": [
                quick_reply_postback_item(t("btn_skip", lang),     make_data("note_skip")),
                quick_reply_postback_item(
                    t("btn_add_note", lang), make_data("note_add"),
                    input_option="openKeyboard",
                ),
                get_back_item(flow, "amount", lang),
                get_cancel_item(lang),
            ]
        },
    }
    await reply_raw_message(reply_token, [message])


async def ask_confirm(reply_token: str, state: dict, lang: str):
    note_display   = state.get("note") or t("label_none", lang)
    amount_display = f"¥{state['amount']:,}" if state.get("amount") is not None else t("label_unknown", lang)
    message = {
        "type": "text",
        "text": t(
            "manual_ask_confirm", lang,
            date=state.get("date",               t("label_unknown", lang)),
            category=f"{state.get('category_icon', '')} {state.get('category_name', t('label_unknown', lang))}",
            payment=f"{state.get('payment_method_icon', '')} {state.get('payment_method_name', t('label_unknown', lang))}",
            amount=amount_display,
            note=note_display,
        ),
        "quickReply": {
            "items": [
                quick_reply_postback_item(t("btn_confirm", lang), make_manual_postback_data("confirm")),
                quick_reply_postback_item(t("btn_restart", lang), make_manual_postback_data("restart")),
                get_back_item("manual", "note", lang),
                get_cancel_item(lang),
            ]
        },
    }
    await reply_raw_message(reply_token, [message])


async def handle_manual_postback(
    reply_token: str, user_id: str, data: dict, postback: dict, state: dict, lang: str
):
    step = data.get("step")

    # ── Back navigation ───────────────────────────────────────────────────

    if step == "back_date":
        if state:
            state["step"] = "date"
            await set_manual_entry_state(user_id, state)
        await ask_date(reply_token, lang)
        return

    if step == "back_category":
        if not state:
            await reply_message(reply_token, t("session_expired", lang))
            return
        state["step"] = "category"
        await set_manual_entry_state(user_id, state)
        await ask_category(reply_token, state["date"], lang)
        return

    if step == "back_payment":
        if not state:
            await reply_message(reply_token, t("session_expired", lang))
            return
        state["step"] = "payment"
        await set_manual_entry_state(user_id, state)
        await ask_payment_method(reply_token, state, lang)
        return

    if step == "back_amount":
        if not state:
            await reply_message(reply_token, t("session_expired", lang))
            return
        state["step"] = "amount"
        await set_manual_entry_state(user_id, state)
        await ask_amount(reply_token, state, lang)
        return

    if step == "back_note":
        if not state:
            await reply_message(reply_token, t("session_expired", lang))
            return
        state["step"] = "note"
        await set_manual_entry_state(user_id, state)
        await ask_note_option(reply_token, lang, flow="manual")
        return

    # ── Forward navigation ────────────────────────────────────────────────

    if step == "date":
        selected_date = postback.get("params", {}).get("date")
        if not selected_date:
            await reply_message(reply_token, t("date_error", lang))
            return
        state.update({"flow": "manual", "step": "category", "date": selected_date, "lang": lang})
        await set_manual_entry_state(user_id, state)
        await ask_category(reply_token, selected_date, lang)
        return

    if step == "category":
        if not state:
            await reply_message(reply_token, t("session_expired", lang))
            return
        category_id = int(data["category_id"])
        category    = find_category(category_id)
        if not category:
            await reply_message(reply_token, t("category_error", lang))
            return
        state.update({
            "step":          "payment",
            "category_id":   category_id,
            "category_name": _cat_name(category, lang),
            "category_icon": category["icon"],
        })
        await set_manual_entry_state(user_id, state)
        await ask_payment_method(reply_token, state, lang)
        return

    if step == "payment":
        if not state:
            await reply_message(reply_token, t("session_expired", lang))
            return
        payment_method_id = int(data["payment_method_id"])
        payment           = find_payment_method(payment_method_id)
        if not payment:
            await reply_message(reply_token, t("payment_error", lang))
            return
        state.update({
            "step":                "amount",
            "payment_method_id":   payment_method_id,
            "payment_method_name": _pay_name(payment, lang),
            "payment_method_icon": payment["icon"],
        })
        await set_manual_entry_state(user_id, state)
        await ask_amount(reply_token, state, lang)
        return

    if step == "note_skip":
        if not state:
            await reply_message(reply_token, t("session_expired", lang))
            return
        state.update({"note": None, "step": "confirm"})
        await set_manual_entry_state(user_id, state)
        await ask_confirm(reply_token, state, lang)
        return

    if step == "note_add":
        if not state:
            await reply_message(reply_token, t("session_expired", lang))
            return
        state["step"] = "note"
        await set_manual_entry_state(user_id, state)
        await reply_message(reply_token, t("enter_note_prompt", lang))
        return

    if step == "confirm":
        if not state:
            await reply_message(reply_token, t("session_expired", lang))
            return
        await save_transaction_from_state(reply_token, user_id, state, lang)
        return

    if step == "restart":
        await delete_manual_entry_state(user_id)
        await start_manual_entry(reply_token, user_id, lang)
        return

    await reply_message(reply_token, t("invalid_action_manual", lang))


async def handle_manual_text_input(
    reply_token: str, user_id: str, text: str, state: dict, lang: str
):
    step = state.get("step")

    if step == "amount":
        amount_text = text.replace(",", "").replace("円", "").replace("¥", "").strip()
        if not amount_text.isdigit():
            await reply_message(reply_token, t("invalid_amount", lang))
            return
        state.update({"amount": int(amount_text), "step": "note"})
        await set_manual_entry_state(user_id, state)
        await ask_note_option(reply_token, lang, flow="manual")
        return

    if step == "note":
        note = text.strip()
        if not note:
            await reply_message(reply_token, t("invalid_note", lang))
            return
        state.update({"note": note, "step": "confirm"})
        await set_manual_entry_state(user_id, state)
        await ask_confirm(reply_token, state, lang)
        return

    await reply_message(reply_token, t("invalid_action_manual", lang))
    await delete_manual_entry_state(user_id)


# ── Receipt flow ───────────────────────────────────────────────────────────

def _build_receipt_review_message(state: dict, lang: str) -> dict:
    date_display     = state.get("date") or t("label_unknown", lang)
    amount_display   = f"¥{state['amount']:,}" if state.get("amount") is not None else t("label_unknown", lang)
    category_display = (
        f"{state['category_icon']} {state['category_name']}"
        if state.get("category_name") else t("label_unknown", lang)
    )
    payment_display  = (
        f"{state['payment_method_icon']} {state['payment_method_name']}"
        if state.get("payment_method_name") else t("label_unknown", lang)
    )
    note_display = state.get("note") or t("label_none", lang)
    return {
        "type": "text",
        "text": t(
            "receipt_review", lang,
            store=state.get("store_name", t("label_unknown", lang)),
            date=date_display,
            category=category_display,
            payment=payment_display,
            amount=amount_display,
            note=note_display,
        ),
        "quickReply": {
            "items": [
                quick_reply_postback_item(t("btn_confirm", lang),  make_receipt_postback_data("confirm_all")),
                quick_reply_postback_item(t("btn_edit", lang),     make_receipt_postback_data("edit")),
                quick_reply_postback_item(t("btn_add_note", lang), make_receipt_postback_data("note_add"), input_option="openKeyboard"),
                get_cancel_item(lang),
            ]
        },
    }


async def ask_receipt_review(reply_token: str, state: dict, lang: str):
    msg = _build_receipt_review_message(state, lang)
    await reply_raw_message(reply_token, [msg])


async def push_receipt_review(user_id: str, state: dict, lang: str):
    msg = _build_receipt_review_message(state, lang)
    await push_raw_message(user_id, [msg])


async def ask_receipt_date(reply_token: str, state: dict, lang: str):
    current_date = state.get("date")
    items = []
    if current_date:
        items.append(quick_reply_postback_item(
            f"✅ {current_date}", make_receipt_postback_data("date_confirm"),
        ))
    items.append({
        "type": "action",
        "action": {
            "type":  "datetimepicker",
            "label": t("btn_other_date", lang),
            "data":  make_receipt_postback_data("date_pick"),
            "mode":  "date",
        },
    })
    items.append(get_back_item("receipt", "review", lang))
    items.append(get_cancel_item(lang))

    message = {
        "type": "text",
        "text": t(
            "receipt_ask_date", lang,
            label_scanned=t("label_scanned", lang),
            date=current_date or t("label_unknown", lang),
        ),
        "quickReply": {"items": items},
    }
    await reply_raw_message(reply_token, [message])


async def ask_receipt_category(reply_token: str, state: dict, lang: str):
    current_id = state.get("category_id")
    items      = []
    if current_id:
        items.append(quick_reply_postback_item(
            f"✅ {state['category_icon']} {state['category_name']}",
            make_receipt_postback_data("category_confirm"),
        ))
    for c in CATEGORIES:
        if c["id"] == current_id:
            continue
        items.append(quick_reply_postback_item(
            f"{c['icon']} {_cat_name(c, lang)}",
            make_receipt_postback_data("category_pick", category_id=str(c["id"])),
        ))
    items.append(get_back_item("receipt", "date", lang))
    items.append(get_cancel_item(lang))

    cat_display = (
        f"{state.get('category_icon', '')} {state.get('category_name', t('label_unknown', lang))}"
    )
    message = {
        "type": "text",
        "text": t(
            "receipt_ask_category", lang,
            label_scanned=t("label_scanned", lang),
            category=cat_display,
        ),
        "quickReply": {"items": items},
    }
    await reply_raw_message(reply_token, [message])


async def ask_receipt_payment(reply_token: str, state: dict, lang: str):
    current_id = state.get("payment_method_id")
    items      = []
    if current_id:
        items.append(quick_reply_postback_item(
            f"✅ {state['payment_method_icon']} {state['payment_method_name']}",
            make_receipt_postback_data("payment_confirm"),
        ))
    for p in PAYMENT_METHODS:
        if p["id"] == current_id:
            continue
        items.append(quick_reply_postback_item(
            f"{p['icon']} {_pay_name(p, lang)}",
            make_receipt_postback_data("payment_pick", payment_method_id=str(p["id"])),
        ))
    items.append(get_back_item("receipt", "category", lang))
    items.append(get_cancel_item(lang))

    payment_display = (
        f"{state.get('payment_method_icon', '')} {state.get('payment_method_name', t('label_unknown', lang))}"
    )
    message = {
        "type": "text",
        "text": t(
            "receipt_ask_payment", lang,
            label_scanned=t("label_scanned", lang),
            payment=payment_display,
        ),
        "quickReply": {"items": items},
    }
    await reply_raw_message(reply_token, [message])


async def ask_receipt_amount(reply_token: str, state: dict, lang: str):
    current_amount = state.get("amount")
    items          = []
    if current_amount is not None:
        items.append(quick_reply_postback_item(
            f"✅ ¥{current_amount:,}", make_receipt_postback_data("amount_confirm"),
        ))
    items.append(quick_reply_postback_item(
        t("btn_edit", lang),
        make_receipt_postback_data("amount_edit"),
        input_option="openKeyboard",
    ))
    items.append(get_back_item("receipt", "payment", lang))
    items.append(get_cancel_item(lang))

    amount_display = f"¥{current_amount:,}" if current_amount is not None else t("label_unknown", lang)
    message = {
        "type": "text",
        "text": t(
            "receipt_ask_amount", lang,
            label_scanned=t("label_scanned", lang),
            amount=amount_display,
        ),
        "quickReply": {"items": items},
    }
    await reply_raw_message(reply_token, [message])


async def ask_receipt_final_confirm(reply_token: str, state: dict, lang: str):
    note_display   = state.get("note") or t("label_none", lang)
    amount_display = f"¥{state['amount']:,}" if state.get("amount") is not None else t("label_unknown", lang)
    message = {
        "type": "text",
        "text": t(
            "receipt_ask_confirm", lang,
            date=state.get("date",               t("label_unknown", lang)),
            category=f"{state.get('category_icon', '')} {state.get('category_name', t('label_unknown', lang))}",
            payment=f"{state.get('payment_method_icon', '')} {state.get('payment_method_name', t('label_unknown', lang))}",
            amount=amount_display,
            note=note_display,
        ),
        "quickReply": {
            "items": [
                quick_reply_postback_item(t("btn_confirm", lang), make_receipt_postback_data("final_confirm")),
                quick_reply_postback_item(t("btn_restart", lang), make_receipt_postback_data("restart")),
                get_back_item("receipt", "note", lang),
                get_cancel_item(lang),
            ]
        },
    }
    await reply_raw_message(reply_token, [message])


async def handle_receipt_postback(
    reply_token: str, user_id: str, data: dict, postback: dict, state: dict, lang: str
):
    step  = data.get("step")

    if not state or state.get("flow") != "receipt":
        await reply_message(reply_token, t("session_expired_receipt", lang))
        return

    # ── Back navigation ───────────────────────────────────────────────────

    if step == "back_review":
        state["step"] = "review"
        await set_manual_entry_state(user_id, state)
        await ask_receipt_review(reply_token, state, lang)
        return

    if step == "back_date":
        state["step"] = "edit_date"
        await set_manual_entry_state(user_id, state)
        await ask_receipt_date(reply_token, state, lang)
        return

    if step == "back_category":
        state["step"] = "edit_category"
        await set_manual_entry_state(user_id, state)
        await ask_receipt_category(reply_token, state, lang)
        return

    if step == "back_payment":
        state["step"] = "edit_payment"
        await set_manual_entry_state(user_id, state)
        await ask_receipt_payment(reply_token, state, lang)
        return

    if step == "back_amount":
        state["step"] = "edit_amount"
        await set_manual_entry_state(user_id, state)
        await ask_receipt_amount(reply_token, state, lang)
        return

    if step == "back_note":
        state["step"] = "edit_note"
        await set_manual_entry_state(user_id, state)
        await ask_note_option(reply_token, lang, flow="receipt")
        return

    # ── Forward navigation ────────────────────────────────────────────────

    if step == "confirm_all":
        await save_transaction_from_state(reply_token, user_id, state, lang)
        return

    if step == "edit":
        state["step"] = "edit_date"
        await set_manual_entry_state(user_id, state)
        await ask_receipt_date(reply_token, state, lang)
        return

    if step == "date_confirm":
        state["step"] = "edit_category"
        await set_manual_entry_state(user_id, state)
        await ask_receipt_category(reply_token, state, lang)
        return

    if step == "date_pick":
        selected_date = postback.get("params", {}).get("date")
        if not selected_date:
            await reply_message(reply_token, t("date_error", lang))
            return
        state.update({"date": selected_date, "step": "edit_category"})
        await set_manual_entry_state(user_id, state)
        await ask_receipt_category(reply_token, state, lang)
        return

    if step == "category_confirm":
        state["step"] = "edit_payment"
        await set_manual_entry_state(user_id, state)
        await ask_receipt_payment(reply_token, state, lang)
        return

    if step == "category_pick":
        category_id = int(data["category_id"])
        category    = find_category(category_id)
        if not category:
            await reply_message(reply_token, t("category_error", lang))
            return
        state.update({
            "category_id":   category["id"],
            "category_name": _cat_name(category, lang),
            "category_icon": category["icon"],
            "step":          "edit_payment",
        })
        await set_manual_entry_state(user_id, state)
        await ask_receipt_payment(reply_token, state, lang)
        return

    if step == "payment_confirm":
        state["step"] = "edit_amount"
        await set_manual_entry_state(user_id, state)
        await ask_receipt_amount(reply_token, state, lang)
        return

    if step == "payment_pick":
        payment_id = int(data["payment_method_id"])
        payment    = find_payment_method(payment_id)
        if not payment:
            await reply_message(reply_token, t("payment_error", lang))
            return
        state.update({
            "payment_method_id":   payment["id"],
            "payment_method_name": _pay_name(payment, lang),
            "payment_method_icon": payment["icon"],
            "step":                "edit_amount",
        })
        await set_manual_entry_state(user_id, state)
        await ask_receipt_amount(reply_token, state, lang)
        return

    if step == "amount_confirm":
        state["step"] = "edit_note"
        await set_manual_entry_state(user_id, state)
        await ask_note_option(reply_token, lang, flow="receipt")
        return

    if step == "amount_edit":
        state["step"] = "edit_amount_input"
        await set_manual_entry_state(user_id, state)
        await reply_message(reply_token, t("enter_amount_prompt", lang))
        return

    if step == "note_skip":
        state.update({"note": None, "step": "edit_confirm"})
        await set_manual_entry_state(user_id, state)
        await ask_receipt_final_confirm(reply_token, state, lang)
        return

    if step == "note_add":
        state["step"] = "review_note_input"
        await set_manual_entry_state(user_id, state)
        await reply_raw_message(reply_token, [{
            "type": "text",
            "text": t("enter_note_prompt", lang),
            "quickReply": {
                "items": [
                    quick_reply_postback_item(t("btn_back", lang), make_receipt_postback_data("back_review")),
                    get_cancel_item(lang),
                ]
            },
        }])
        return

    if step == "final_confirm":
        await save_transaction_from_state(reply_token, user_id, state, lang)
        return

    if step == "restart":
        await delete_manual_entry_state(user_id)
        await reply_message(reply_token, t("restart_receipt", lang))
        return

    await reply_message(reply_token, t("invalid_action", lang))


async def handle_receipt_text_input(
    reply_token: str, user_id: str, text: str, state: dict, lang: str
):
    step = state.get("step")

    if step == "edit_amount_input":
        amount_text = text.replace(",", "").replace("円", "").replace("¥", "").strip()
        if not amount_text.isdigit():
            await reply_message(reply_token, t("invalid_amount", lang))
            return
        state.update({"amount": int(amount_text), "step": "edit_note"})
        await set_manual_entry_state(user_id, state)
        await ask_note_option(reply_token, lang, flow="receipt")
        return

    if step == "edit_note_input":
        note = text.strip()
        if not note:
            await reply_message(reply_token, t("invalid_note", lang))
            return
        state.update({"note": note, "step": "edit_confirm"})
        await set_manual_entry_state(user_id, state)
        await ask_receipt_final_confirm(reply_token, state, lang)
        return

    if step == "review_note_input":
        note = text.strip()
        if not note:
            await reply_message(reply_token, t("invalid_note", lang))
            return
        state.update({"note": note, "step": "review"})
        await set_manual_entry_state(user_id, state)
        await ask_receipt_review(reply_token, state, lang)
        return

    await reply_message(reply_token, t("invalid_action", lang))
    await delete_manual_entry_state(user_id)


# ── Save ───────────────────────────────────────────────────────────────────

async def save_transaction_from_state(
    reply_token: str, user_id: str, state: dict, lang: str
):
    try:
        date_str      = state.get("date")
        transacted_at = datetime.strptime(date_str, "%Y-%m-%d") if date_str else datetime.now()
        note          = state.get("note")

        await save_transaction(
            uid=user_id,
            amount=state["amount"],
            transacted_at=transacted_at,
            category_id=state.get("category_id"),
            payment_method_id=state.get("payment_method_id"),
            receipt_image_url=None,
            note=note,
        )
        await delete_manual_entry_state(user_id)

        amount_display = f"¥{state['amount']:,}" if state.get("amount") is not None else t("label_unknown", lang)
        await reply_message(
            reply_token,
            t(
                "saved_ok", lang,
                date=state.get("date",               t("label_unknown", lang)),
                category=f"{state.get('category_icon', '')} {state.get('category_name', t('label_unknown', lang))}",
                payment=f"{state.get('payment_method_icon', '')} {state.get('payment_method_name', t('label_unknown', lang))}",
                amount=amount_display,
                note=note or t("label_none", lang),
            ),
        )
    except Exception:
        traceback.print_exc()
        await reply_message(reply_token, t("save_failed", lang))
