"""Document parsers.

Each parser lives in its own module and lazily imports its heavy third-party
dependency, so this package (and the wider service) imports cleanly even when
``pypdf``/``python-docx``/``bs4`` are not installed.
"""

from __future__ import annotations

from rag_service.exceptions import UnsupportedFormatError
from rag_service.pipeline.parser.base import Parser, ParseResult

__all__ = ["Parser", "ParseResult", "PARSER_REGISTRY", "get_parser", "detect_source_type"]


def _load_registry() -> dict[str, type[Parser]]:
    from rag_service.pipeline.parser.docx import DOCXParser
    from rag_service.pipeline.parser.html import HTMLParser
    from rag_service.pipeline.parser.markdown import MarkdownParser
    from rag_service.pipeline.parser.pdf import PDFParser
    from rag_service.pipeline.parser.pptx import PPTXParser
    from rag_service.pipeline.parser.text import PlainTextParser
    from rag_service.pipeline.parser.url import URLParser

    return {
        "pdf": PDFParser,
        "pptx": PPTXParser,
        "docx": DOCXParser,
        "md": MarkdownParser,
        "markdown": MarkdownParser,
        "html": HTMLParser,
        "htm": HTMLParser,
        "txt": PlainTextParser,
        "text": PlainTextParser,
        "url": URLParser,
    }


PARSER_REGISTRY: dict[str, type[Parser]] = _load_registry()


def get_parser(source_type: str) -> Parser:
    cls = PARSER_REGISTRY.get((source_type or "").lower())
    if cls is None:
        raise UnsupportedFormatError(source_type)
    return cls()


def detect_source_type(name_or_url: str) -> str:
    value = (name_or_url or "").strip()
    if value.lower().startswith(("http://", "https://")):
        return "url"
    # Take the final path segment in case a URL-like string slipped through.
    tail = value.rsplit("/", 1)[-1]
    if "." in tail:
        ext = tail.rsplit(".", 1)[-1].lower()
        return ext
    return ""
