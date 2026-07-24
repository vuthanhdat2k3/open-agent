"""URL parser.

Fetches a remote URL with :mod:`httpx` and delegates to the appropriate parser
based on the response ``content-type`` (HTML/PDF -> specialised parsers,
otherwise plain text).
"""

from __future__ import annotations

from rag_service.exceptions import ParseError
from rag_service.pipeline.base import Parser, ParseResult

__all__ = ["URLParser"]

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)


class URLParser(Parser):
    """Fetch a URL and parse its content by detected content type."""

    async def parse(self, source: bytes | str, **kwargs: object) -> ParseResult:
        if not isinstance(source, str):
            raise ParseError("URLParser expects a URL string")
        url = source.strip()
        if not url:
            raise ParseError("URLParser received an empty URL")

        try:
            import httpx  # type: ignore
        except ImportError as exc:
            raise ParseError("URL parsing requires 'httpx' to be installed") from exc

        try:
            async with httpx.AsyncClient(
                follow_redirects=True,
                timeout=30.0,
                headers={"User-Agent": _USER_AGENT},
            ) as client:
                resp = await client.get(url, allow_redirects=True)
        except Exception as exc:
            raise ParseError(f"Failed to fetch URL {url!r}: {exc}") from exc

        if resp.status_code >= 400:
            raise ParseError(
                f"URL {url!r} returned HTTP status {resp.status_code}"
            )

        content_type = (resp.headers.get("content-type") or "").lower()
        metadata: dict[str, object] = {"source_url": url}

        if "application/pdf" in content_type:
            from rag_service.pipeline.parser.pdf import PDFParser

            result = await PDFParser().parse(resp.content)
        elif "text/html" in content_type:
            from rag_service.pipeline.parser.html import HTMLParser

            result = await HTMLParser().parse(resp.content)
        else:
            from rag_service.pipeline.parser.text import PlainTextParser

            text = resp.text if isinstance(resp.text, str) else resp.content.decode("utf-8", errors="ignore")
            result = await PlainTextParser().parse(text)

        merged = dict(metadata)
        merged.update(result.metadata)
        return ParseResult(text=result.text, metadata=merged)
