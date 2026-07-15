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

__all__ = ["PDFParser"]

_USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"


class PDFParser(Parser):
    """Parse PDF ``bytes`` into plain text plus metadata."""

    async def parse(self, source: bytes | str, **kwargs: object) -> ParseResult:
        if isinstance(source, str):
            source = source.encode("utf-8", errors="ignore")

        if not source:
            raise ParseError("PDF source is empty")

        try:
            import io

            import pypdf  # type: ignore

            reader = pypdf.PdfReader(io.BytesIO(source))
            pages: list[str] = []
            for page in reader.pages:
                try:
                    pages.append(page.extract_text() or "")
                except Exception as exc:  # pragma: no cover - defensive
                    logger.warning("pypdf failed on a page: %s", exc)
                    pages.append("")

            low_text = sum(1 for p in pages if len(p.strip()) < 30)
            if low_text and low_text >= len(pages) / 2:
                try:
                    from pdfminer.high_level import extract_text

                    text = extract_text(io.BytesIO(source))
                    if text and text.strip():
                        pages = [text]
                except Exception as exc:  # pragma: no cover - optional dep
                    logger.warning("pdfminer fallback unavailable: %s", exc)

            page_count = len(reader.pages)
            info = reader.metadata or {}
            metadata = _build_metadata(info, page_count)
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
