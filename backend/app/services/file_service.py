from __future__ import annotations

import asyncio
import base64
import os
import re
import uuid

import boto3
from botocore.exceptions import ClientError
from fastapi import UploadFile
from sqlalchemy import select

from app.config import get_settings
from app.mcp.client import get_mcp_manager
from app.models.files import UploadedFile
from app.models.mcp import McpServer
from app.repositories.files_repo import UploadedFileRepository


def _extract_document_id(text: str) -> str | None:
    m = re.search(r"Document ID:\s*(\S+)", text or "")
    return m.group(1) if m else None


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

    async def ingest_to_rag(
        self,
        org_id: str,
        id: str,
        collection: str,
        chunk_size: int,
        chunk_overlap: int,
        tags: list[str],
    ) -> dict:
        record = await self.repo.get(org_id, id)
        if record is None:
            raise ValueError("file not found")
        try:
            def _download() -> bytes:
                obj = self._s3_client().get_object(Bucket=self.settings.s3_bucket, Key=record.stored_path)
                return obj["Body"].read()

            data = await asyncio.to_thread(_download)
            content_base64 = base64.b64encode(data).decode("ascii")
            res = await self.db.execute(
                select(McpServer).where(
                    McpServer.org_id == org_id,
                    McpServer.name == self.settings.rag_mcp_server_name,
                )
            )
            server = res.scalar_one_or_none()
            if server is None:
                raise ValueError(
                    f"RAG MCP server '{self.settings.rag_mcp_server_name}' not "
                    "configured. Add it under MCP settings."
                )
            raw = await get_mcp_manager().call_tool(
                server,
                "rag_ingest_file",
                {
                    "filename": record.original_name,
                    "content_base64": content_base64,
                    "collection": collection,
                    "tags": tags,
                    "chunk_size": chunk_size,
                    "chunk_overlap": chunk_overlap,
                },
            )
            document_id = _extract_document_id(raw)
            record.status = "ingested"
            record.collection = collection
            record.error = None
            self.db.add(record)
            await self.db.commit()
            return {"ok": True, "result": raw, "document_id": document_id}
        except Exception as e:  # noqa: BLE001
            record.status = "error"
            record.error = str(e)
            self.db.add(record)
            await self.db.commit()
            raise ValueError(str(e))
