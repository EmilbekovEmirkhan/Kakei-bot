from dotenv import load_dotenv
load_dotenv()

import os

CHANNEL_ACCESS_TOKEN = os.environ.get("CHANNEL_ACCESS_TOKEN", "")
CHANNEL_SECRET       = os.environ.get("CHANNEL_SECRET", "")
GEMINI_API_KEY       = os.environ.get("GEMINI_API_KEY", "")
DATABASE_URL         = os.environ.get("DATABASE_URL", "")