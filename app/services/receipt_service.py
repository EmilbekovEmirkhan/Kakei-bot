"""
Receipt service — Gemini 2.5 Flash
Takes raw image bytes, returns structured dict and formatted reply.
"""

import json

from io import BytesIO
from PIL import Image, ImageOps
from google import genai
from app.config import GEMINI_API_KEY


_PROMPT: str = """
Parse this Japanese receipt.

Return ONLY valid JSON:
{
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
Use final paid total, not subtotal.
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
        api_key = GEMINI_API_KEY
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is not set")
        _client = genai.Client(api_key=api_key)
    return _client


def parse_receipt_bytes(image_bytes: bytes, mime_type: str = "image/jpeg") -> dict:
    response = _get_client().models.generate_content(
        model="gemini-2.5-flash",
        contents=[
            genai.types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
            _PROMPT,
        ],
        config={
            "temperature": 0,
            "response_mime_type": "application/json",
        },
    )

    raw = response.text.strip()

    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1]
        raw = raw.rsplit("```", 1)[0].strip()

    data = json.loads(raw)

    normalized = {
        "category_id": data.get("c"),
        "amount": data.get("a"),
        "date": data.get("d"),
        "payment_method_id": data.get("p"),
    }

    if normalized.get("category_id") is not None:
        normalized["category_id"] = int(normalized["category_id"])

    if normalized.get("payment_method_id") is not None:
        normalized["payment_method_id"] = int(normalized["payment_method_id"])

    if normalized.get("amount") is not None:
        normalized["amount"] = int(normalized["amount"])

    return normalized

def optimize_receipt_image(
    image_bytes: bytes,
    max_width: int = 640,
    jpeg_quality: int = 70,
) -> tuple[bytes, str]:
    image = Image.open(BytesIO(image_bytes))

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