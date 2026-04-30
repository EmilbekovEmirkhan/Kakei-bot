"""
Local test — no LINE API, no deployment needed.

Usage:
    python3 tests/test_receipt.py receipt.jpg
"""

import json
import sys
from pathlib import Path
from app.services.receipt_service import parse_receipt_bytes, format_receipt_reply

SUPPORTED_MIME = {
    ".jpg":  "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png":  "image/png",
    ".webp": "image/webp",
    ".dng":  "image/jpeg",
}


def main():
    args = sys.argv[1:]

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


if __name__ == "__main__":
    main()