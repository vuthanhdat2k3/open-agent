"""Plain text parser.

Decodes ``bytes`` as UTF-8 (optionally using ``chardet`` to detect encoding
when available) and returns the text unchanged.
"""

from __future__ import annotations

from rag_service.pipeline.base import Parser, ParseResult

__all__ = ["PlainTextParser"]


class PlainTextParser(Parser):
    """Parse plain-text ``bytes``/``str``."""

    async def parse(self, source: bytes | str, **kwargs: object) -> ParseResult:
        if isinstance(source, str):
            text = source
        else:
            text = _decode(source)
        return ParseResult(text=text, metadata={})


def _decode(data: bytes) -> str:
    try:
        import chardet  # type: ignore

        result = chardet.detect(data)
        encoding = result.get("encoding") if result else None
        if encoding:
            return data.decode(encoding, errors="ignore")
    except ImportError:  # pragma: no cover - optional dependency
        pass
    except Exception:  # pragma: no cover - defensive
        pass
    return data.decode("utf-8", errors="ignore")
