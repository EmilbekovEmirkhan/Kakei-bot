import asyncio
import boto3
from botocore.exceptions import BotoCoreError, ClientError
from datetime import datetime
from app.config import AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_S3_BUCKET, AWS_REGION, ENV

_s3_client = None

def get_s3_client():
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client(
            "s3",
            region_name=AWS_REGION,
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        )
    return _s3_client


async def upload_receipt_image(uid: str, image_bytes: bytes, message_id: str) -> str:
    """Upload receipt image to S3 and return the object URL."""
    now = datetime.now()
    key = f"receipts/{ENV}/{uid}/{now.year}/{now.month:02d}/{now.strftime('%Y%m%d_%H%M%S')}_{message_id}.jpg"

    try:
        s3 = get_s3_client()
        await asyncio.to_thread(
            s3.put_object,
            Bucket=AWS_S3_BUCKET,
            Key=key,
            Body=image_bytes,
            ContentType="image/jpeg",
        )
        return key

    except (BotoCoreError, ClientError) as e:
        raise RuntimeError(f"S3 upload failed: {e}") from e
    
def delete_receipt_image(s3_key: str) -> None:
    """Delete a receipt image from S3."""
    try:
        s3 = get_s3_client()
        s3.delete_object(Bucket=AWS_S3_BUCKET, Key=s3_key)
    except (BotoCoreError, ClientError) as e:
        raise RuntimeError(f"S3 delete failed: {e}") from e
    
def generate_presigned_url(s3_key: str, expires_in: int = 3600) -> str:
    """Generate a temporary URL valid for `expires_in` seconds (default 1 hour)."""
    s3 = get_s3_client()
    return s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": AWS_S3_BUCKET, "Key": s3_key},
        ExpiresIn=expires_in,
    )