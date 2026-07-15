"""Chunker registry and factory."""

from __future__ import annotations

from rag_service.config import settings
from rag_service.pipeline.base import Chunker
from rag_service.pipeline.chunker.recursive import RecursiveCharacterChunker
from rag_service.pipeline.chunker.sentence import SentenceChunker
from rag_service.pipeline.chunker.token import TokenChunker

CHUNKER_REGISTRY: dict[str, type[Chunker]] = {
    "recursive": RecursiveCharacterChunker,
    "sentence": SentenceChunker,
    "token": TokenChunker,
}


def get_chunker(name: str | None, chunk_size: int, chunk_overlap: int) -> Chunker:
    key = (name or settings.default_chunker or "recursive").lower()
    cls = CHUNKER_REGISTRY.get(key, RecursiveCharacterChunker)
    return cls(chunk_size=chunk_size, chunk_overlap=chunk_overlap)


__all__ = [
    "RecursiveCharacterChunker",
    "SentenceChunker",
    "TokenChunker",
    "CHUNKER_REGISTRY",
    "get_chunker",
]
