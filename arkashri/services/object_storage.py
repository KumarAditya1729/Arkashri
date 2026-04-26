from __future__ import annotations

import os
import inspect
import uuid
from dataclasses import dataclass
from typing import Any

import aiofiles
import aiofiles.os

from arkashri.config import get_settings


class ObjectStorageError(RuntimeError):
    pass


@dataclass
class StoredObject:
    uri: str
    bucket: str | None
    key: str
    provider: str


def _safe_name(filename: str) -> str:
    return os.path.basename(filename or "artifact").replace(" ", "_")


class LocalObjectStorage:
    def __init__(self, base_dir: str):
        self.base_dir = base_dir

    async def save_bytes(self, *, key: str, content: bytes, content_type: str | None = None) -> StoredObject:
        path = os.path.join(self.base_dir, key)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        async with aiofiles.open(path, "wb") as handle:
            await handle.write(content)
        return StoredObject(uri=path, bucket=None, key=key, provider="local")

    async def read_bytes(self, uri: str) -> bytes:
        async with aiofiles.open(uri, "rb") as handle:
            return await handle.read()

    async def delete(self, uri: str) -> None:
        try:
            await aiofiles.os.remove(uri)
        except FileNotFoundError:
            return

    async def presigned_url(self, uri: str, *, expires_in: int = 3600) -> str:
        return uri


class S3ObjectStorage:
    def __init__(self, *, bucket: str, region: str):
        self.bucket = bucket
        self.region = region

    def _parse_uri(self, uri: str) -> str:
        prefix = f"s3://{self.bucket}/"
        if not uri.startswith(prefix):
            raise ObjectStorageError("S3 URI does not match configured bucket.")
        return uri[len(prefix):]

    def _client_kwargs(self) -> dict[str, Any]:
        settings = get_settings()
        kwargs: dict[str, Any] = {"region_name": self.region}
        if settings.aws_access_key_id and settings.aws_secret_access_key:
            kwargs["aws_access_key_id"] = settings.aws_access_key_id
            kwargs["aws_secret_access_key"] = settings.aws_secret_access_key
        return kwargs

    async def _client(self):
        try:
            import aiobotocore.session
        except ImportError as exc:
            raise ObjectStorageError("aiobotocore is required for S3 object storage.") from exc
        return aiobotocore.session.get_session().create_client("s3", **self._client_kwargs())

    async def save_bytes(self, *, key: str, content: bytes, content_type: str | None = None) -> StoredObject:
        async with await self._client() as client:
            await client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=content,
                ContentType=content_type or "application/octet-stream",
                ServerSideEncryption="AES256",
            )
        return StoredObject(uri=f"s3://{self.bucket}/{key}", bucket=self.bucket, key=key, provider="s3")

    async def read_bytes(self, uri: str) -> bytes:
        key = self._parse_uri(uri)
        async with await self._client() as client:
            response = await client.get_object(Bucket=self.bucket, Key=key)
            async with response["Body"] as stream:
                return await stream.read()

    async def delete(self, uri: str) -> None:
        key = self._parse_uri(uri)
        async with await self._client() as client:
            await client.delete_object(Bucket=self.bucket, Key=key)

    async def presigned_url(self, uri: str, *, expires_in: int = 3600) -> str:
        key = self._parse_uri(uri)
        async with await self._client() as client:
            result = client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket, "Key": key},
                ExpiresIn=expires_in,
            )
            if inspect.isawaitable(result):
                return await result
            return result


class ObjectStorageService:
    def __init__(self):
        self.settings = get_settings()

    def _backend(self, *, bucket: str | None = None):
        provider = self.settings.storage_provider.lower()
        if provider == "s3":
            resolved_bucket = bucket or self.settings.evidence_s3_bucket
            if not resolved_bucket:
                raise ObjectStorageError("S3 storage is enabled but no bucket is configured.")
            return S3ObjectStorage(bucket=resolved_bucket, region=self.settings.aws_region)
        return LocalObjectStorage(self.settings.upload_dir)

    async def save_bytes(
        self,
        *,
        tenant_id: str,
        category: str,
        filename: str,
        content: bytes,
        content_type: str | None = None,
        bucket: str | None = None,
    ) -> StoredObject:
        key = f"{category}/{tenant_id}/{uuid.uuid4()}_{_safe_name(filename)}"
        return await self._backend(bucket=bucket).save_bytes(key=key, content=content, content_type=content_type)

    async def read_bytes(self, uri: str, *, bucket: str | None = None) -> bytes:
        return await self._backend(bucket=bucket).read_bytes(uri)

    async def delete(self, uri: str, *, bucket: str | None = None) -> None:
        await self._backend(bucket=bucket).delete(uri)

    async def presigned_url(self, uri: str, *, expires_in: int = 3600, bucket: str | None = None) -> str:
        return await self._backend(bucket=bucket).presigned_url(uri, expires_in=expires_in)


object_storage_service = ObjectStorageService()
