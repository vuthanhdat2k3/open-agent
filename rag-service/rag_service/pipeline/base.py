"""Pipeline base types & abstract interfaces.

This module is the *contract* the whole service is built on. Concrete parsers,
chunkers and embedders (implemented elsewhere) subclass these ABCs, so the
orchestrator, services and tests can depend on a stable interface.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# Data structures
# --------------------------------------------------------------------------- #
def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _short_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:8]}"


@dataclass
class TextChunk:
    """A text segment produced by the chunker.

    ``metadata`` carries everything needed downstream for storage & retrieval:
    at minimum ``document_id``, ``collection_id``, ``source_type``, ``tags``,
    ``source_name`` and ``token_count``.
    """

    text: str
    chunk_id: str = field(default_factory=lambda: _short_id("chunk"))
    start_char: int = 0
    end_char: int = 0
    chunk_index: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ParseResult:
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


class IngestOptions(BaseModel):
    """Per-ingest configuration."""

    chunker: str | None = None  # "recursive" | "sentence" | "token"
    chunk_size: int = Field(default=800, ge=1)
    chunk_overlap: int = Field(default=150, ge=0)
    enable_graph: bool = False
    tags: list[str] = Field(default_factory=list)
    custom_metadata: dict[str, Any] = Field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Parser
# --------------------------------------------------------------------------- #
class Parser(abc.ABC):
    @abc.abstractmethod
    async def parse(self, source: bytes | str, **kwargs: Any) -> ParseResult:
        """Parse ``source`` into plain text + metadata."""


# --------------------------------------------------------------------------- #
# Chunker
# --------------------------------------------------------------------------- #
class Chunker(abc.ABC):
    def __init__(self, chunk_size: int = 800, chunk_overlap: int = 150, **_: Any) -> None:
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    @abc.abstractmethod
    def chunk(self, text: str, doc_metadata: dict[str, Any], **kwargs: Any) -> list[TextChunk]:
        """Split ``text`` into :class:`TextChunk` objects."""


# --------------------------------------------------------------------------- #
# Embedder
# --------------------------------------------------------------------------- #
class Embedder(abc.ABC):
    model: str = "unknown"
    dimensions: int = 0

    @abc.abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding vector per input text."""

    @abc.abstractmethod
    async def embed_query(self, text: str) -> list[float]:
        """Embed a single query string."""

    async def embed_batch(
        self, texts: list[str], batch_size: int = 100
    ) -> list[list[float]]:
        """Default batched embedding; embedders may override for API limits."""
        out: list[list[float]] = []
        for i in range(0, len(texts), batch_size):
            out.extend(await self.embed(texts[i : i + batch_size]))
        return out
