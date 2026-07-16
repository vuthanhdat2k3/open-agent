from __future__ import annotations

import base64
import os
import re
import uuid

from fastapi import UploadFile
from sqlalchemy import select

from app.config import get_settings
from app.db.base import utc_now
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

    def _ensure_upload_dir(self) -> str:
        path = self.settings.upload_dir
        os.makedirs(path, exist_ok=True)
        return path

    async def save_upload(self, file: UploadFile) -> UploadedFile:
        ext = os.path.splitext(file.filename or "")[1].lower()
        if ext and ext not in self.settings.allowed_extensions:
            raise ValueError(f"Unsupported file type: {ext or 'unknown'}")
        data = await file.read()
        if len(data) > self.settings.max_upload_size:
            raise ValueError(
                f"File too large: {len(data)} bytes (max {self.settings.max_upload_size})"
            )
        upload_dir = self._ensure_upload_dir()
        stored_name = f"{uuid.uuid4().hex}{ext}"
        stored_path = os.path.join(upload_dir, stored_name)
        with open(stored_path, "wb") as f:
            f.write(data)
        record = UploadedFile(
            filename=stored_name,
            original_name=file.filename or stored_name,
            content_type=file.content_type or "",
            size=len(data),
            stored_path=stored_path,
            status="uploaded",
        )
        return await self.repo.create(record)

    async def list(self) -> list[UploadedFile]:
        return await self.repo.list()

    async def get(self, id: str) -> UploadedFile | None:
        return await self.repo.get(id)

    async def delete(self, id: str) -> bool:
        record = await self.repo.get(id)
        if record is None:
            return False
        if record.stored_path and os.path.exists(record.stored_path):
            try:
                os.remove(record.stored_path)
            except OSError:
                pass
        return await self.repo.delete(id)

    async def ingest_to_rag(
        self,
        id: str,
        collection: str,
        chunk_size: int,
        chunk_overlap: int,
        tags: list[str],
    ) -> dict:
        record = await self.repo.get(id)
        if record is None:
            raise ValueError("file not found")
        try:
            with open(record.stored_path, "rb") as f:
                data = f.read()
            content_base64 = base64.b64encode(data).decode("ascii")
            res = await self.db.execute(
                select(McpServer).where(
                    McpServer.name == self.settings.rag_mcp_server_name
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
