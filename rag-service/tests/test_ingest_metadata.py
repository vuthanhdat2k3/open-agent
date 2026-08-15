from __future__ import annotations

import pytest

from rag_service.api.v1.routes.ingest import IngestTextRequest
from rag_service.services.ingest_service import IngestService


def test_ingest_text_request_accepts_structured_metadata() -> None:
    request = IngestTextRequest(
        text="briefing",
        title="Acme briefing",
        metadata={"org_id": "org-1", "case_id": "case-1", "source_urls": ["https://example.com"]},
    )

    assert request.metadata == {
        "org_id": "org-1",
        "case_id": "case-1",
        "source_urls": ["https://example.com"],
    }


@pytest.mark.asyncio
async def test_ingest_service_passes_custom_metadata_to_pipeline() -> None:
    service = object.__new__(IngestService)
    captured: dict = {}

    async def fake_create_and_run(**kwargs):
        captured.update(kwargs)
        return {"document_id": "doc-1", "status": "success", "chunk_count": 1, "collection": "ci-knowledge-org"}

    service._create_and_run = fake_create_and_run
    result = await service.ingest_text(
        "briefing text",
        "Acme briefing",
        "ci-knowledge-org",
        tags=["customer-intelligence"],
        chunk_size=800,
        chunk_overlap=150,
        custom_metadata={"org_id": "org-1", "case_id": "case-1"},
    )

    assert result["document_id"] == "doc-1"
    assert captured["custom_metadata"] == {"org_id": "org-1", "case_id": "case-1"}
