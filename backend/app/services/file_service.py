from __future__ import annotations

import asyncio
import hashlib
import os
import uuid

import boto3
from botocore.exceptions import ClientError
from fastapi import UploadFile

from app.config import get_settings
from app.models.files import UploadedFile
from app.repositories.files_repo import UploadedFileRepository


class FileService:
    def __init__(self, db):
        self.db = db
        self.repo = UploadedFileRepository(db)
        self.settings = get_settings()

    def _s3_client(self):
        return boto3.client(
            "s3",
            endpoint_url=self.settings.s3_endpoint_url,
            aws_access_key_id=self.settings.s3_access_key,
            aws_secret_access_key=self.settings.s3_secret_key,
            region_name=self.settings.s3_region,
        )

    def _ensure_bucket(self, client) -> None:
        try:
            client.head_bucket(Bucket=self.settings.s3_bucket)
        except ClientError:
            client.create_bucket(Bucket=self.settings.s3_bucket)

    async def save_upload(
        self, org_id: str, file: UploadFile, user_id: str | None = None
    ) -> UploadedFile:
        ext = os.path.splitext(file.filename or "")[1].lower()
        if ext and ext not in self.settings.allowed_extensions:
            raise ValueError(f"Unsupported file type: {ext or 'unknown'}")
        data = await file.read()
        if len(data) > self.settings.max_upload_size:
            raise ValueError(
                f"File too large: {len(data)} bytes (max {self.settings.max_upload_size})"
            )
        stored_name = f"{uuid.uuid4().hex}{ext}"
        object_key = f"{org_id}/{stored_name}"

        def _upload() -> None:
            client = self._s3_client()
            self._ensure_bucket(client)
            client.put_object(Bucket=self.settings.s3_bucket, Key=object_key, Body=data)

        await asyncio.to_thread(_upload)
        record = UploadedFile(
            org_id=org_id,
            created_by_user_id=user_id,
            filename=stored_name,
            original_name=file.filename or stored_name,
            content_type=file.content_type or "",
            size=len(data),
            file_sha256=hashlib.sha256(data).hexdigest(),
            stored_path=object_key,
            status="uploaded",
        )
        return await self.repo.create(record)

    async def list(self, org_id: str) -> list[UploadedFile]:
        return await self.repo.list(org_id)

    async def get(self, org_id: str, id: str) -> UploadedFile | None:
        return await self.repo.get(org_id, id)

    async def delete(self, org_id: str, id: str) -> bool:
        record = await self.repo.get(org_id, id)
        if record is None:
            return False
        if record.stored_path:

            def _delete() -> None:
                self._s3_client().delete_object(Bucket=self.settings.s3_bucket, Key=record.stored_path)

            try:
                await asyncio.to_thread(_delete)
            except ClientError:
                pass
        return await self.repo.delete(org_id, id)
