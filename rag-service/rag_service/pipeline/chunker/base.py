"""Chunker base re-exports and helpers."""

from __future__ import annotations

from rag_service.pipeline.base import Chunker, TextChunk


def make_chunk(
    text: str,
    index: int,
    start: int,
    end: int,
    metadata: dict,
) -> TextChunk:
    """Build a :class:`TextChunk`, leaving ``chunk_id`` to auto-generate."""
    return TextChunk(
        text=text,
        chunk_index=index,
        start_char=start,
        end_char=end,
        metadata=metadata,
    )


__all__ = ["Chunker", "TextChunk", "make_chunk"]
