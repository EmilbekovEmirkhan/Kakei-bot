"""
Local test — no Line API, no deployment needed.

Usage:
    python3 test_receipt.py receipt.jpg          # parse only
    python3 test_receipt.py receipt.jpg --save   # parse + save to DB
"""

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from receipt_parser import parse_receipt_bytes, format_receipt_reply

load_dotenv()

TEST_USER_ID = "test_user_local"

SUPPORTED_MIME = {
    ".jpg":  "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png":  "image/png",
    ".webp": "image/webp",
    ".dng":  "image/jpeg",  # treat DNG as jpeg for Gemini
}

async def save_test(result: dict):
    from database import (
        init_db, close_pool,
        upsert_user,
        save_transaction,
        get_category_id_by_name,
        get_payment_method_id_by_name,
        get_or_create_place,
    )

    await init_db()
    await upsert_user(TEST_USER_ID, "Test User", "", "ja")

    category_id = await get_category_id_by_name(result.get("category"))
    payment_id  = await get_payment_method_id_by_name(result.get("payment_method"))
    place_id    = await get_or_create_place(result.get("store_name"), category_id) if result.get("store_name") else None
    amount       = result.get("amount") or 0
    tax_amount   = result.get("tax_amount")
    total_amount = result.get("total_amount") or amount

    tx_id = await save_transaction(
        user_id=TEST_USER_ID,
        date=result.get("date") or datetime.today().strftime("%Y-%m-%d"),
        amount=amount,
        tax_amount=tax_amount,
        total_amount=total_amount,
        category_id=category_id,
        place_id=place_id,
        payment_method_id=payment_id,
    )
    print(f"\n── Saved to DB ───────────────────────────")
    print(f"transaction id : {tx_id}")
    print(f"user_id        : {TEST_USER_ID}")
    print(f"\nTo clean up run:")
    print(f"  DELETE FROM transactions WHERE id = {tx_id};")
    print(f"  DELETE FROM users WHERE line_user_id = '{TEST_USER_ID}';")

    await close_pool()


def main():
    save = "--save" in sys.argv
    args = [a for a in sys.argv[1:] if a != "--save"]

    if args:
        image_path = Path(args[0])
    else:
        image_path = Path(input("Receipt image path: ").strip().strip('"'))

    if not image_path.exists():
        print(f"File not found: {image_path}")
        sys.exit(1)

    mime = SUPPORTED_MIME.get(image_path.suffix.lower(), "image/jpeg")
    image_bytes = image_path.read_bytes()

    print(f"Parsing: {image_path}  ({len(image_bytes):,} bytes)\n")

    try:
        result = parse_receipt_bytes(image_bytes, mime)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

    print("── Raw JSON ──────────────────────────────")
    print(json.dumps(result, ensure_ascii=False, indent=2))

    print("\n── Formatted reply ───────────────────────")
    print(format_receipt_reply(result))

    if save:
        asyncio.run(save_test(result))

if __name__ == "__main__":
    main()
