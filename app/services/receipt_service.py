"""
Receipt service — Gemini 2.5 Flash
Takes raw image bytes, returns structured dict and formatted reply.
"""

import json
from google import genai
from app.config import GEMINI_API_KEY
from app.constants import CATEGORIES, PAYMENT_METHODS


_PROMPT: str = f"""
You are a receipt parser specialized in Japanese convenience store and retail receipts.

Analyze this receipt image and extract the transaction information.

You must choose the category_id from this list:
{json.dumps(CATEGORIES, ensure_ascii=False)}

You must choose the payment_method_id from this list:
{json.dumps(PAYMENT_METHODS, ensure_ascii=False)}

Return ONLY valid JSON — no markdown, no code blocks, just raw JSON.

Schema:
{{
  "store_name": "store name as printed on receipt",
  "category_id": integer or null,
  "amount": final total paid as integer in yen including tax,
  "date": "YYYY-MM-DD" or null if not found,
  "payment_method_id": integer or null,
  "items": [
    {{
      "name": "item name",
      "price": integer or null
    }}
  ]
}}

Rules:
- category_id must be one of the provided category IDs.
- payment_method_id must be one of the provided payment method IDs.
- If the payment method is Suica, PASMO, IC, nanaco, WAON, iD, QUICPay, Rakuten Edy, or similar, use 電子マネー.
- If the payment method is PayPay, Rakuten Pay, d払い, au PAY, LINE Pay, Merpay, or similar, use QRコード.
- If the receipt says cash, 現金, お預り, or change/お釣り, use 現金.
- If the receipt says credit, Visa, Mastercard, JCB, AMEX, or card, use クレジットカード.
- If unsure about payment method, use 不明.
- If unsure about category, use その他.
- amount must be the final paid total, not subtotal.
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
    )

    raw = response.text.strip()

    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1]
        raw = raw.rsplit("```", 1)[0].strip()

    data = json.loads(raw)

    # Defensive normalization
    if data.get("category_id") is not None:
        data["category_id"] = int(data["category_id"])

    if data.get("payment_method_id") is not None:
        data["payment_method_id"] = int(data["payment_method_id"])

    if data.get("amount") is not None:
        data["amount"] = int(data["amount"])

    return data
