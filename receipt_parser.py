"""
Receipt parser — Gemini 2.5 Flash
Takes raw image bytes, returns structured dict.
"""

import json
import os
from google import genai

PROMPT = """
You are a receipt parser specialized in Japanese convenience store and retail receipts.
Analyze this receipt image and extract the following fields.

Return ONLY valid JSON — no markdown, no code blocks, just raw JSON.

Schema:
{
  "store_name": "store name as printed on receipt",
  "category": one of ["食費", "交通費", "日用品", "カフェ", "外食", "ショッピング", "その他"],
  "amount": subtotal before tax as integer in yen,
  "tax_amount": tax amount as integer in yen or null,
  "total_amount": final total including tax as integer in yen,
  "date": "YYYY-MM-DD" or null if not found,
  "payment_method": one of ["現金", "クレジットカード", "電子マネー", "QRコード", "不明"],
  "items": [{"name": "item name", "price": 0}]
}

If a field cannot be determined, use null.
"""

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        api_key = os.environ.get("GEMINI_API_KEY", "")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is not set in .env")
        _client = genai.Client(api_key=api_key)
    return _client


def parse_receipt_bytes(image_bytes: bytes, mime_type: str = "image/jpeg") -> dict:
    response = _get_client().models.generate_content(
        model="gemini-2.5-flash",
        contents=[
            genai.types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
            PROMPT,
        ],
    )

    raw = response.text.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1]
        raw = raw.rsplit("```", 1)[0].strip()

    return json.loads(raw)


def format_receipt_reply(data: dict) -> str:
    lines = []

    if data.get("store_name"):
        lines.append(f"🏪 {data['store_name']}")
    if data.get("category"):
        lines.append(f"📂 {data['category']}")
    if data.get("date"):
        lines.append(f"📅 {data['date']}")
    if data.get("total_amount") is not None:
        lines.append(f"💴 ¥{data['total_amount']:,}")
    if data.get("payment_method"):
        lines.append(f"💳 {data['payment_method']}")

    if data.get("items"):
        lines.append("\n明細:")
        for item in data["items"]:
            name = item.get("name", "?")
            price = item.get("price")
            lines.append(f"  • {name}  ¥{price:,}" if price is not None else f"  • {name}")

    return "\n".join(lines)
