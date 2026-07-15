"""Markdown parser.

Strips an optional YAML frontmatter block (``--- ... ---``) at the top of the
document and exposes it as metadata. Uses ``python-frontmatter`` when present,
otherwise a small built-in ``---`` parser.
"""

from __future__ import annotations

from rag_service.core.logging import logger
from rag_service.pipeline.base import Parser, ParseResult

__all__ = ["MarkdownParser"]


class MarkdownParser(Parser):
    """Parse markdown ``bytes``/``str`` into body text + frontmatter metadata."""

    async def parse(self, source: bytes | str, **kwargs: object) -> ParseResult:
        text = source.decode("utf-8", errors="ignore") if isinstance(source, bytes) else source

        body, metadata = _split_frontmatter(text)
        return ParseResult(text=body, metadata=metadata)


def _split_frontmatter(text: str) -> tuple[str, dict[str, object]]:
    stripped = text.lstrip("\ufeff")
    if not stripped.startswith("---"):
        return text, {}

    # python-frontmatter handles nested YAML safely when available.
    try:
        import frontmatter  # type: ignore

        post = frontmatter.loads(text)
        body = post.content
        meta: dict[str, object] = dict(post.metadata)
        return body, meta
    except ImportError:  # pragma: no cover - optional dependency
        logger.debug("python-frontmatter not installed; using built-in frontmatter parser")
    except Exception as exc:  # pragma: no cover - malformed frontmatter
        logger.warning("frontmatter parse failed, treating as plain markdown: %s", exc)
        return text, {}

    body, meta = _manual_frontmatter(stripped)
    return body, meta


def _manual_frontmatter(text: str) -> tuple[str, dict[str, object]]:
    lines = text.splitlines()
    # lines[0] == "---"
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return text, {}

    meta: dict[str, object] = {}
    for raw in lines[1:end]:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            meta[key] = value

    body = "\n".join(lines[end + 1 :]).strip("\n")
    return body, meta
