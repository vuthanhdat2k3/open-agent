from __future__ import annotations

import os

import httpx

from app.config import get_settings

# ponytail: hard char cap keeps one attachment from blowing the prompt
# budget; raise if real usage needs longer documents inlined.
MAX_ATTACHMENT_PROMPT_CHARS = 20_000

_TEXT_EXTS = {".txt", ".md", ".csv", ".json", ".py", ".yaml", ".yml", ".html", ".htm"}


async def extract_text(data: bytes, filename: str) -> str:
    """Best-effort plain-text extraction to inline a chat attachment into the
    prompt for this turn only. Never writes to the RAG index — ingestion is a
    separate, explicit action (rag_ingest_file / POST /api/files/{id}/ingest).
    """
    ext = os.path.splitext(filename)[1].lower()
    if ext in _TEXT_EXTS:
        text = data.decode("utf-8", errors="replace")
    else:
        settings = get_settings()
        if not settings.docling_service_url:
            return f"[could not read '{filename}': document extraction service is not configured]"
        try:
            async with httpx.AsyncClient(timeout=90.0) as client:
                resp = await client.post(
                    f"{settings.docling_service_url.rstrip('/')}/convert",
                    files={"file": (filename, data, "application/octet-stream")},
                )
                resp.raise_for_status()
                payload = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            return f"[could not read '{filename}': {exc}]"
        text = payload.get("text")
        if not isinstance(text, str):
            return f"[could not read '{filename}': extraction service returned no text]"

    if len(text) > MAX_ATTACHMENT_PROMPT_CHARS:
        text = text[:MAX_ATTACHMENT_PROMPT_CHARS] + "\n...[truncated]"
    return text
