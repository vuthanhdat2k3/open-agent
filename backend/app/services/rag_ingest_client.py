from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import BinaryIO

import httpx


class RagIngestError(RuntimeError):
    def __init__(self, code: str, detail: str, *, retryable: bool = False):
        super().__init__(detail)
        self.code = code
        self.detail = detail[:1000]
        self.retryable = retryable


@dataclass(frozen=True)
class RagIngestResult:
    document_id: str
    chunk_count: int
    provenance: dict


class RagIngestClient:
    def __init__(self, settings):
        self.settings = settings

    async def ingest(
        self, body: BinaryIO, *, filename: str, content_type: str,
        collection: str, chunk_size: int, chunk_overlap: int,
        tags: list[str], correlation_id: str,
    ) -> RagIngestResult:
        timeout = httpx.Timeout(
            connect=self.settings.rag_ingest_connect_timeout_seconds,
            read=self.settings.rag_ingest_read_timeout_seconds,
            write=self.settings.rag_ingest_read_timeout_seconds,
            pool=self.settings.rag_ingest_connect_timeout_seconds,
        )
        url = self.settings.rag_service_url.rstrip("/") + "/api/v1/ingest/file"
        headers = {"X-Correlation-ID": correlation_id}
        if self.settings.rag_api_key:
            headers["X-API-Key"] = self.settings.rag_api_key
        data = {
            "collection": collection,
            "chunk_size": str(chunk_size),
            "chunk_overlap": str(chunk_overlap),
            "tags": json.dumps(tags),
        }
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    url, headers=headers, data=data,
                    files={"file": (filename, body, content_type or "application/octet-stream")},
                )
        except (httpx.TimeoutException, httpx.NetworkError, asyncio.TimeoutError) as exc:
            raise RagIngestError("RAG_UNAVAILABLE", "rag-service request failed", retryable=True) from exc
        except httpx.HTTPError as exc:
            raise RagIngestError("RAG_REQUEST_FAILED", "rag-service request failed", retryable=True) from exc
        if response.status_code == 429 or response.status_code >= 500:
            raise RagIngestError("RAG_TEMPORARY_FAILURE", f"rag-service returned HTTP {response.status_code}", retryable=True)
        if response.status_code in (401, 403):
            raise RagIngestError("RAG_AUTH_FAILED", "rag-service authentication failed")
        if response.status_code >= 400:
            raise RagIngestError("RAG_REJECTED", f"rag-service rejected the file (HTTP {response.status_code})")
        try:
            payload = response.json()
        except ValueError as exc:
            raise RagIngestError("INVALID_RAG_RESULT", "rag-service returned invalid JSON") from exc
        if payload.get("status") not in {"success", "already_exists"}:
            raise RagIngestError("INVALID_RAG_RESULT", "rag-service did not report success")
        document_id = str(payload.get("document_id") or "").strip()
        chunk_count = payload.get("chunk_count")
        if not document_id or not isinstance(chunk_count, int) or chunk_count <= 0:
            raise RagIngestError("INVALID_RAG_RESULT", "rag-service returned no stored chunks")
        return RagIngestResult(document_id, chunk_count, payload.get("provenance") or {})
