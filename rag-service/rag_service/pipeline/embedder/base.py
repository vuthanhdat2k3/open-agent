"""Embedder base class with retry/backoff.

Concrete embedders implement the two sync/async primitives ``_embed`` and
``_embed_query``; this class wraps them with exponential-backoff retries driven
by :data:`rag_service.config.settings`.
"""

from __future__ import annotations

import asyncio

from rag_service.config import settings
from rag_service.exceptions import EmbeddingError
from rag_service.pipeline.base import Embedder


class BaseEmbedder(Embedder):
    """Retry wrapper around a concrete embedding backend."""

    async def embed(self, texts: list[str]) -> list[list[float]]:
        last_exc: Exception | None = None
        attempts = max(1, settings.embed_retry_attempts)
        delay = settings.embed_retry_delay
        for attempt in range(attempts):
            try:
                return await self._embed(texts)
            except EmbeddingError:
                raise
            except Exception as exc:  # noqa: BLE001 - wrap all backend errors
                last_exc = exc
                if attempt < attempts - 1:
                    await asyncio.sleep(delay * (2**attempt))
        raise EmbeddingError(
            f"Embedding failed after {attempts} attempts", detail=str(last_exc)
        )

    async def embed_query(self, text: str) -> list[float]:
        last_exc: Exception | None = None
        attempts = max(1, settings.embed_retry_attempts)
        delay = settings.embed_retry_delay
        for attempt in range(attempts):
            try:
                return await self._embed_query(text)
            except EmbeddingError:
                raise
            except Exception as exc:  # noqa: BLE001 - wrap all backend errors
                last_exc = exc
                if attempt < attempts - 1:
                    await asyncio.sleep(delay * (2**attempt))
        raise EmbeddingError(
            f"Query embedding failed after {attempts} attempts", detail=str(last_exc)
        )

    async def _embed(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError

    async def _embed_query(self, text: str) -> list[float]:
        raise NotImplementedError
