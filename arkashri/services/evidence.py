import uuid
import os
import shutil
from typing import Protocol
from starlette.datastructures import UploadFile

from arkashri.config import get_settings

class StorageBackend(Protocol):
    async def save_file(self, tenant_id: str, file: UploadFile) -> str:
        ...

    async def get_file_content(self, file_path: str) -> bytes:
        ...


class LocalStorageBackend:
    def __init__(self, base_dir: str = "/tmp/arkashri_evidence"):
        self.base_dir = base_dir
        os.makedirs(self.base_dir, exist_ok=True)

    async def save_file(self, tenant_id: str, file: UploadFile) -> str:
        tenant_dir = os.path.join(self.base_dir, tenant_id)
        os.makedirs(tenant_dir, exist_ok=True)
        
        file_ext = os.path.splitext(file.filename)[1] if file.filename else ""
        file_name = f"{uuid.uuid4()}{file_ext}"
        file_path = os.path.join(tenant_dir, file_name)
        
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        return file_path

    async def get_file_content(self, file_path: str) -> bytes:
        with open(file_path, "rb") as buffer:
            return buffer.read()


class S3StorageBackend:
    def __init__(self, bucket_name: str):
        self.bucket_name = bucket_name
        # Intentionally left unimplemented - requires boto3 setup.
        # This is a structural mock for enterprise readiness demonstrating the interface.

    async def save_file(self, tenant_id: str, file: UploadFile) -> str:
        file_ext = os.path.splitext(file.filename)[1] if file.filename else ""
        file_key = f"{tenant_id}/{uuid.uuid4()}{file_ext}"
        # Example logic: s3_client.upload_fileobj(file.file, self.bucket_name, file_key)
        return f"s3://{self.bucket_name}/{file_key}"

    async def get_file_content(self, file_path: str) -> bytes:
        # Example logic: response = s3_client.get_object(Bucket=self.bucket_name, Key=file_path)
        # return response['Body'].read()
        return b""


class EvidenceService:
    def __init__(self):
        get_settings()
        # In a real enterprise app, we'd check if AWS S3 is configured, else fallback
        # e.g., if settings.s3_bucket: self.backend = S3StorageBackend(settings.s3_bucket)
        self.backend = LocalStorageBackend()

    async def upload_evidence(self, tenant_id: str, file: UploadFile) -> str:
        return await self.backend.save_file(tenant_id, file)

    async def get_evidence_content(self, file_path: str) -> bytes:
        return await self.backend.get_file_content(file_path)

evidence_service = EvidenceService()
