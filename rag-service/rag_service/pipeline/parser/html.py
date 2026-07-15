"""HTML parser.

Converts HTML to markdown with :mod:`BeautifulSoup` + :mod:`markdownify`, with
a minimal regex tag-stripper fallback so the service still boots/works without
``bs4`` installed.
"""

from __future__ import annotations

from rag_service.core.logging import logger
from rag_service.pipeline.base import Parser, ParseResult

__all__ = ["HTMLParser"]


class HTMLParser(Parser):
    """Parse HTML ``bytes``/``str`` into markdown text + extracted metadata."""

    async def parse(self, source: bytes | str, **kwargs: object) -> ParseResult:
        text = source.decode("utf-8", errors="ignore") if isinstance(source, bytes) else source
        if not text.strip():
            return ParseResult(text="", metadata={})

        try:
            from bs4 import BeautifulSoup  # type: ignore

            soup = BeautifulSoup(text, "html.parser")
            for tag in soup(["script", "style", "nav", "footer", "noscript"]):
                tag.decompose()

            metadata = _extract_meta(soup, is_bs4=True)

            from markdownify import markdownify  # type: ignore

            body = markdownify(str(soup), heading_style="ATX")
        except ImportError:
            logger.debug("bs4/markdownify not installed; using regex tag-strip fallback")
            body, metadata = _regex_fallback(text)

        body = body.strip()
        return ParseResult(text=body, metadata=metadata)


def _extract_meta(soup: object, *, is_bs4: bool) -> dict[str, object]:
    meta: dict[str, object] = {}
    if not is_bs4:
        return meta
    try:
        title_tag = soup.title  # type: ignore[attr-defined]
        if title_tag and title_tag.string:
            meta["title"] = str(title_tag.string).strip()
        for tag in soup.find_all("meta"):  # type: ignore[attr-defined]
            name = (tag.get("name") or "").lower()
            content = tag.get("content")
            if not content:
                continue
            if name == "description":
                meta["description"] = str(content)
            elif name == "author":
                meta["author"] = str(content)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Failed to extract HTML metadata: %s", exc)
    return meta


def _regex_fallback(html: str) -> tuple[str, dict[str, object]]:
    import re

    meta: dict[str, object] = {}

    title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    if title_match:
        meta["title"] = _clean(title_match.group(1))

    for name in ("description", "author"):
        m = re.search(
            rf'<meta[^>]+name=["\']{name}["\'][^>]+content=["\'](.*?)["\']',
            html,
            re.IGNORECASE | re.DOTALL,
        )
        if m:
            meta[name] = _clean(m.group(1))

    # Strip scripts/styles/comments then tags.
    cleaned = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.IGNORECASE | re.DOTALL)
    cleaned = re.sub(r"<!--.*?-->", " ", cleaned, flags=re.DOTALL)
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    cleaned = re.sub(r"&nbsp;", " ", cleaned)
    cleaned = re.sub(r"&amp;", "&", cleaned)
    cleaned = re.sub(r"&lt;", "<", cleaned)
    cleaned = re.sub(r"&gt;", ">", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip(), meta


def _clean(value: str) -> str:
    import re

    return re.sub(r"\s+", " ", value).strip()
