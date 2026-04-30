"""
Receipt service — Gemini 2.5 Flash
Takes raw image bytes, returns structured dict and formatted reply.
"""

import json
from google import genai
from app.config import GEMINI_API_KEY

PROMPT = """
You are a receipt parser specialized in Japanese convenience store and retail receipts.
Analyze this receipt image and extract the following fields.

Return ONLY valid JSON — no markdown, no code blocks, just raw JSON.

Schema:
{
  "store_name": "store name as printed on receipt",
  "category": one of ["食費", "交通費", "日用品", "カフェ", "外食", "ショッピング", "その他"],
  "amount": final total paid as integer in yen including tax,
  "date": "YYYY-MM-DD" or null if not found,
  "payment_method": one of ["現金", "クレジットカード", "電子マネー", "QRコード", "不明"],
  "items": [{"name": "item name", "price": integer or null}]
}

If a field cannot be determined, use null.
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
    if data.get("amount") is not None:
        lines.append(f"💴 ¥{data['amount']:,}")
    if data.get("payment_method"):
        lines.append(f"💳 {data['payment_method']}")

    if data.get("items"):
        lines.append("\n明細:")
        for item in data["items"]:
            name = item.get("name", "?")
            price = item.get("price")
            lines.append(f"  • {name}  ¥{price:,}" if price is not None else f"  • {name}")

    return "\n".join(lines)