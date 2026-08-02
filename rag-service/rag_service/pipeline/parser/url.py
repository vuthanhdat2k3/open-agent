"""URL parser.

Fetches a remote URL with :mod:`httpx` and delegates to the appropriate parser
based on the response ``content-type`` (HTML/PDF -> specialised parsers,
otherwise plain text).
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

from rag_service.exceptions import ParseError
from rag_service.pipeline.base import Parser, ParseResult

__all__ = ["URLParser"]

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

MAX_FETCH_REDIRECTS = 5
MAX_FETCH_BYTES = 25 * 1024 * 1024


def _safe_fetch_url(url: str) -> bool:
    """Reject URLs whose host resolves to a non-public IP (SSRF guard).

    Blocks loopback/private/link-local (incl. cloud metadata 169.254.169.254)
    /reserved/multicast/unspecified addresses — same class of internal
    services (qdrant, redis, other docker-network containers) an
    attacker-controlled ingest URL could otherwise reach.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return False
    try:
        addrs = socket.getaddrinfo(parsed.hostname, None)
    except socket.gaierror:
        return False
    for _, _, _, _, sockaddr in addrs:
        ip = ipaddress.ip_address(sockaddr[0])
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            return False
    return True


class URLParser(Parser):
    """Fetch a URL and parse its content by detected content type."""

    async def parse(self, source: bytes | str, **kwargs: object) -> ParseResult:
        if not isinstance(source, str):
            raise ParseError("URLParser expects a URL string")
        url = source.strip()
        if not url:
            raise ParseError("URLParser received an empty URL")
        if not _safe_fetch_url(url):
            raise ParseError(f"URL {url!r} blocked (must be http/https and resolve to a public address)")

        try:
            import httpx  # type: ignore
        except ImportError as exc:
            raise ParseError("URL parsing requires 'httpx' to be installed") from exc

        try:
            # follow_redirects=False + manual hop validation: a redirect
            # Location is attacker-influenced same as the original URL, so
            # each hop must pass the SSRF check too (auto-follow would let a
            # safe URL redirect into an internal/metadata address).
            async with httpx.AsyncClient(timeout=30.0, headers={"User-Agent": _USER_AGENT}) as client:
                for _ in range(MAX_FETCH_REDIRECTS):
                    resp = await client.get(url, follow_redirects=False)
                    if resp.status_code in (301, 302, 303, 307, 308) and "location" in resp.headers:
                        next_url = str(httpx.URL(url).join(resp.headers["location"]))
                        if not _safe_fetch_url(next_url):
                            raise ParseError(f"Redirect target {next_url!r} blocked by SSRF guard")
                        url = next_url
                        continue
                    break
            if len(resp.content) > MAX_FETCH_BYTES:
                raise ParseError(f"URL {url!r} response exceeds {MAX_FETCH_BYTES} bytes")
        except ParseError:
            raise
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
