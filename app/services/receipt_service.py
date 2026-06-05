"""
Receipt service — Gemini 2.5 Flash

Takes raw image bytes and returns a normalized transaction dict:
{
    "store_name": str | None,
    "category_id": int | None,
    "amount": int | None,
    "date": str | None,
    "payment_method_id": int | None,
}
"""

import json
import re
import asyncio
from io import BytesIO

from PIL import Image, ImageOps
from google import genai

from app.config import GEMINI_API_KEY


_PROMPT: str = """
Parse this Japanese receipt.

Return ONLY valid JSON:
{
  "s": store name string or null,
  "c": category id or null,
  "a": final paid total integer yen or null,
  "d": "YYYY-MM-DD" or null,
  "p": payment method id or null
}

Categories:
1 食費, 2 交通費, 3 日用品, 4 カフェ, 5 外食, 6 ショッピング, 7 その他

Payment:
1 現金, 2 クレジットカード, 3 電子マネー, 4 QRコード, 5 不明

Rules:
For store name, return the merchant/store name as text. If unclear, return null.
For the amount, use the 合計 or 小計 line (the bill total the customer owes).
NEVER use 現金/お預り (cash tendered) or お釣り (change) as the amount.
If category unsure, use 7.
If payment unsure, use 5.
IC/Suica/PASMO/nanaco/WAON/iD/QUICPay/Edy = 3.
PayPay/Rakuten Pay/d払い/au PAY/LINE Pay/Merpay = 4.
Visa/Mastercard/JCB/AMEX/card/クレジット = 2.
現金/お預り/お釣り = 1.
"""

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client

    if _client is None:
        if not GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY is not set")

        _client = genai.Client(api_key=GEMINI_API_KEY)

    return _client

def _strip_markdown_json(raw: str) -> str:
    """
    Gemini should return pure JSON because response_mime_type is application/json,
    but this keeps the parser safe if markdown fences appear anyway.
    """
    raw = raw.strip()

    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1]
        raw = raw.rsplit("```", 1)[0].strip()

    return raw

def _safe_int(value) -> int | None:
    """
    Converts values like:
    1280
    "1280"
    "1,280"
    "¥1,280"
    "1280円"

    Returns None if conversion is impossible.
    """
    if value is None:
        return None

    if isinstance(value, int):
        return value

    if isinstance(value, float):
        return int(value)

    if isinstance(value, str):
        cleaned = re.sub(r"[^\d]", "", value)

        if not cleaned:
            return None

        return int(cleaned)

    return None

def _normalize_store_name(value) -> str | None:
    if not isinstance(value, str):
        return None

    store_name = value.strip()

    if not store_name:
        return None

    return store_name

def _normalize_category_id(value) -> int | None:
    category_id = _safe_int(value)

    if category_id in range(1, 8):
        return category_id

    return None

def _normalize_payment_method_id(value) -> int | None:
    payment_method_id = _safe_int(value)

    if payment_method_id in range(1, 6):
        return payment_method_id

    return None

def _normalize_date(value) -> str | None:
    """
    Keeps only valid-looking YYYY-MM-DD strings.
    This does not fully validate real calendar dates, but prevents obvious junk.
    """
    if not isinstance(value, str):
        return None

    value = value.strip()

    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return value

    return None

def parse_receipt_bytes(image_bytes: bytes, mime_type: str = "image/jpeg") -> dict:
    response = _get_client().models.generate_content(
        model="gemini-2.5-flash",
        contents=[
            genai.types.Part.from_bytes(
                data=image_bytes,
                mime_type=mime_type,
            ),
            _PROMPT,
        ],
        config={
            "temperature": 0,
            "response_mime_type": "application/json",
        },
    )

    if not response.text:
        raise ValueError("Gemini returned an empty response")

    raw = _strip_markdown_json(response.text)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Gemini returned invalid JSON: {raw}") from exc

    if not isinstance(data, dict):
        raise ValueError(f"Gemini returned non-object JSON: {data}")

    return {
        "store_name": _normalize_store_name(data.get("s")),
        "category_id": _normalize_category_id(data.get("c")),
        "amount": _safe_int(data.get("a")),
        "date": _normalize_date(data.get("d")),
        "payment_method_id": _normalize_payment_method_id(data.get("p")),
    }


def optimize_receipt_image(
    image_bytes: bytes,
    max_width: int = 640,
    jpeg_quality: int = 70,
) -> tuple[bytes, str]:
    with Image.open(BytesIO(image_bytes)) as image:
        image = ImageOps.exif_transpose(image)
        image = image.convert("RGB")

        if image.width > max_width:
            ratio = max_width / image.width
            new_height = int(image.height * ratio)
            image = image.resize((max_width, new_height))

        output = BytesIO()
        image.save(
            output,
            format="JPEG",
            quality=jpeg_quality,
            optimize=True,
        )

    return output.getvalue(), "image/jpeg"

async def parse_receipt_image_async(
    image_bytes: bytes,
    max_width: int = 768,
    jpeg_quality: int = 75,
) -> dict:
    optimized_bytes, mime_type = await asyncio.to_thread(
        optimize_receipt_image,
        image_bytes,
        max_width,
        jpeg_quality,
    )

    parsed = await asyncio.to_thread(
        parse_receipt_bytes,
        optimized_bytes,
        mime_type,
    )

    return parsed