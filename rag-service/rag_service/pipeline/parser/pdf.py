"""PDF parser.

Uses :mod:`pypdf` when available (preferred) and falls back to
:func:`pdfminer.high_level.extract_text` from ``pdfminer.six`` for pages that
yield little text. Both heavy dependencies are imported lazily so this module
imports cleanly even when neither library is installed.
"""

from __future__ import annotations

from rag_service.core.logging import logger
from rag_service.exceptions import ParseError
from rag_service.pipeline.base import Parser, ParseResult
from rag_service.pipeline.parser.docling_client import DoclingServiceError, parse_with_docling, service_url

__all__ = ["PDFParser"]

_USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"


class PDFParser(Parser):
    """Parse PDF ``bytes`` into plain text plus metadata."""

    async def parse(self, source: bytes | str, **kwargs: object) -> ParseResult:
        if isinstance(source, str):
            source = source.encode("utf-8", errors="ignore")

        if not source:
            raise ParseError("PDF source is empty")

        metadata_prefix: dict[str, object] = {}
        try:
            import pdf_inspector  # type: ignore

            classification = pdf_inspector.classify_pdf_bytes(source)
            pdf_type = str(getattr(classification, "pdf_type", "")).lower()
            confidence = float(getattr(classification, "confidence", 1.0))
            metadata_prefix["pdf_classification"] = pdf_type
            metadata_prefix["pdf_classification_confidence"] = confidence
            needs_docling = pdf_type in {"scanned", "image_based", "mixed"} or confidence < 0.75
            if needs_docling:
                if service_url():
                    try:
                        text, docling_metadata = await parse_with_docling(source, "document.pdf")
                        docling_metadata.setdefault("parser", "docling")
                        docling_metadata.update(metadata_prefix)
                        return ParseResult(text=text, metadata=docling_metadata)
                    except DoclingServiceError as exc:
                        metadata_prefix["warnings"] = [
                            "scanned PDF, OCR service unavailable; text may be incomplete"
                        ]
                        logger.warning("docling_unavailable_falling_back", error=str(exc))
                else:
                    metadata_prefix["warnings"] = [
                        "scanned PDF, OCR not configured; text may be incomplete"
                    ]
        except (ImportError, OSError, ValueError, TypeError) as exc:
            logger.warning("pdf_inspector_unavailable", error=str(exc))

        try:
            import io

            import pypdf  # type: ignore

            reader = pypdf.PdfReader(io.BytesIO(source))
            pages: list[str] = []
            for page in reader.pages:
                try:
                    text = ""
                    try:
                        text = page.extract_text(extraction_mode="layout") or ""
                    except Exception:
                        text = page.extract_text() or ""
                    pages.append(text)
                except Exception as exc:  # pragma: no cover - defensive
                    logger.warning("pypdf failed on a page: %s", exc)
                    pages.append("")

            page_count = len(reader.pages)
            info = reader.metadata or {}
            metadata = _build_metadata(info, page_count)
        except ImportError:
            try:
                import io

                from pdfminer.high_level import extract_text

                text = extract_text(io.BytesIO(source)) or ""
                pages = [text] if text.strip() else []
                page_count = len(pages)
                metadata = {"page_count": page_count}
            except ImportError as exc:
                raise ParseError(
                    "PDF parsing requires 'pypdf' or 'pdfminer.six' to be installed"
                ) from exc

        body = ""
        for idx, page_text in enumerate(pages, start=1):
            if idx > 1:
                body += "\n<!-- page {} -->\n".format(idx)
            body += page_text

        metadata["page_count"] = metadata.get("page_count") or len(pages)
        metadata.update(metadata_prefix)
        return ParseResult(text=body, metadata=metadata)


def _build_metadata(info: object, page_count: int) -> dict[str, object]:
    def _get(key: str) -> object:
        for attr in (key, "/" + key):
            value = getattr(info, attr, None)
            if value is not None and str(value).strip():
                return str(value)
        return None

    meta: dict[str, object] = {}
    title = _get("Title")
    if title:
        meta["title"] = title
    author = _get("Author")
    if author:
        meta["author"] = author
    creator = _get("Creator")
    if creator:
        meta["creator"] = creator
    created = _get("CreationDate")
    if created:
        meta["created_at"] = created
    meta["page_count"] = page_count
    return meta
