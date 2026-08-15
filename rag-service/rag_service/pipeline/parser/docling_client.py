"""Small REST client for the optional Docling extraction service."""

from __future__ import annotations

import os
from typing import Any

import httpx


class DoclingServiceError(RuntimeError):
    """Raised when the optional Docling service cannot extract a document."""


def service_url() -> str:
    return os.environ.get("DOCLING_SERVICE_URL", "").strip().rstrip("/")


def service_timeout() -> float:
    try:
        return max(1.0, float(os.environ.get("DOCLING_SERVICE_TIMEOUT_SECONDS", "90")))
    except ValueError:
        return 90.0


async def parse_with_docling(source: bytes, filename: str) -> tuple[str, dict[str, Any]]:
    url = service_url()
    if not url:
        raise DoclingServiceError("DOCLING_SERVICE_URL is not configured")

    try:
        async with httpx.AsyncClient(timeout=service_timeout()) as client:
            response = await client.post(
                f"{url}/convert",
                files={"file": (filename, source, "application/octet-stream")},
            )
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise DoclingServiceError(str(exc)) from exc

    if not isinstance(payload, dict):
        raise DoclingServiceError("Docling response was not a JSON object")
    text = payload.get("text") or payload.get("markdown")
    if not isinstance(text, str):
        document = payload.get("document")
        if isinstance(document, dict):
            text = document.get("md_content") or document.get("text")
    if not isinstance(text, str):
        raise DoclingServiceError("Docling response did not contain extracted text")
    metadata = payload.get("metadata")
    return text, metadata if isinstance(metadata, dict) else {}
