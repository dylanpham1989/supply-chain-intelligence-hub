import asyncio
from pathlib import Path
from typing import Any

import boto3
from botocore.client import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import settings
from app.core.errors import ServiceUnavailableError
from app.core.logging import get_logger

log = get_logger(__name__)

PRESIGN_TTL_S = 300


class ObjectStore:
    """One client for MinIO locally and S3 in a deployment.

    boto3 is synchronous, so every call goes to a thread rather than stalling
    the event loop.
    """

    def __init__(self) -> None:
        self._client: Any = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            region_name=settings.s3_region,
            config=Config(signature_version="s3v4", retries={"max_attempts": 3}),
        )
        self.bucket = settings.s3_bucket

    async def ping(self) -> None:
        """Readiness only. A missing bucket is as good as an unreachable store."""
        await asyncio.to_thread(self._client.head_bucket, Bucket=self.bucket)

    async def ensure_bucket(self) -> None:
        await asyncio.to_thread(self._ensure_bucket_sync)

    def _ensure_bucket_sync(self) -> None:
        try:
            self._client.head_bucket(Bucket=self.bucket)
        except ClientError:
            try:
                self._client.create_bucket(Bucket=self.bucket)
                log.info("storage.bucket_created", bucket=self.bucket)
            except ClientError as exc:
                if exc.response.get("Error", {}).get("Code") not in (
                    "BucketAlreadyOwnedByYou",
                    "BucketAlreadyExists",
                ):
                    raise

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        try:
            await asyncio.to_thread(
                self._client.put_object,
                Bucket=self.bucket,
                Key=key,
                Body=data,
                ContentType=content_type,
            )
        except (BotoCoreError, ClientError) as exc:
            log.warning("storage.put_failed", key=key, error=str(exc))
            raise ServiceUnavailableError("Document storage is unavailable") from exc

    async def download_to(self, key: str, destination: Path) -> None:
        try:
            await asyncio.to_thread(self._client.download_file, self.bucket, key, str(destination))
        except (BotoCoreError, ClientError) as exc:
            raise ServiceUnavailableError(f"Cannot read {key}") from exc

    async def delete(self, key: str) -> None:
        try:
            await asyncio.to_thread(self._client.delete_object, Bucket=self.bucket, Key=key)
        except (BotoCoreError, ClientError) as exc:
            log.warning("storage.delete_failed", key=key, error=str(exc))

    async def presigned_url(self, key: str, ttl_s: int = PRESIGN_TTL_S) -> str:
        url: str = await asyncio.to_thread(
            self._client.generate_presigned_url,
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=ttl_s,
        )
        return url


_store: ObjectStore | None = None


def get_store() -> ObjectStore:
    global _store
    if _store is None:
        _store = ObjectStore()
    return _store
