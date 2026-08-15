"""PPTX parser backed by the optional Docling service."""

from __future__ import annotations

from rag_service.pipeline.base import Parser, ParseResult
from rag_service.pipeline.parser.docling_client import DoclingServiceError, parse_with_docling

__all__ = ["PPTXParser"]


class PPTXParser(Parser):
    async def parse(self, source: bytes | str, **kwargs: object) -> ParseResult:
        if isinstance(source, str):
            source = source.encode("utf-8", errors="ignore")
        try:
            text, metadata = await parse_with_docling(source, "document.pptx")
            metadata.setdefault("parser", "docling")
            return ParseResult(text=text, metadata=metadata)
        except DoclingServiceError as exc:
            return ParseResult(
                text="",
                metadata={
                    "warnings": [f"PPTX extraction unavailable: {exc}"],
                    "parser": "docling",
                },
            )
