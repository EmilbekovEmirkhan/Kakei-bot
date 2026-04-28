"""
Local test — no Line API, no deployment needed.

Usage:
    python3 test_receipt.py receipt.jpg
    python3 test_receipt.py              # will prompt for path
"""

import json
import sys
from pathlib import Path
from dotenv import load_dotenv
from receipt_parser import parse_receipt_bytes, format_receipt_reply

load_dotenv()

SUPPORTED_MIME = {
    ".jpg":  "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png":  "image/png",
    ".webp": "image/webp",
    ".dng":  "image/jpeg",  # treat DNG as jpeg for Gemini
}

def main():
    if len(sys.argv) > 1:
        image_path = Path(sys.argv[1])
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
