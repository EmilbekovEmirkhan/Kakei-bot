from dotenv import load_dotenv
load_dotenv()

import os

ENV = os.environ.get("ENV", "dev")

CHANNEL_ACCESS_TOKEN = os.environ.get("CHANNEL_ACCESS_TOKEN", "")
CHANNEL_SECRET       = os.environ.get("CHANNEL_SECRET", "")
GEMINI_API_KEY       = os.environ.get("GEMINI_API_KEY", "")
DATABASE_URL         = os.environ.get("DATABASE_URL", "")
REDIS_URL            = os.environ.get("REDIS_URL", "")
LIFF_ID              = os.environ.get("LIFF_ID", "")

AWS_ACCESS_KEY_ID     = os.environ.get("AWS_ACCESS_KEY_ID", "")
AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY", "")
AWS_S3_BUCKET         = os.environ.get("AWS_S3_BUCKET", "")
AWS_REGION            = os.environ.get("AWS_REGION", "")