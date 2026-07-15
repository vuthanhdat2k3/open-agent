"""Sentence-Transformers embeddings embedder (local models)."""

from __future__ import annotations

import asyncio
from typing import Any

from rag_service.config import settings
from rag_service.core.logging import logger
from rag_service.exceptions import EmbeddingError
from rag_service.pipeline.embedder.base import BaseEmbedder


class SentenceTransformerEmbedder(BaseEmbedder):
    def __init__(self, **_: Any) -> None:
        from sentence_transformers import SentenceTransformer

        try:
            self._model = SentenceTransformer(settings.st_model)
        except Exception as exc:  # noqa: BLE001 - let factory fall back
            logger.warning("Failed to load SentenceTransformer model %r: %s",
                           settings.st_model, exc)
            raise EmbeddingError(
                f"Could not load sentence-transformers model {settings.st_model!r}",
                detail=str(exc),
            )
        self.model = settings.st_model
        self.dimensions = self._model.get_sentence_embedding_dimension()

    async def _embed(self, texts: list[str]) -> list[list[float]]:
        try:
            emb = await asyncio.to_thread(
                self._model.encode, texts, normalize_embeddings=True
            )
            return [list(map(float, v)) for v in emb.tolist()]
        except EmbeddingError:
            raise
        except Exception as exc:  # noqa: BLE001 - surface as EmbeddingError
            logger.warning("SentenceTransformer embed failed: %s", exc)
            raise EmbeddingError("sentence-transformers embedding failed", detail=str(exc))

    async def _embed_query(self, text: str) -> list[float]:
        try:
            emb = await asyncio.to_thread(
                self._model.encode, [text], normalize_embeddings=True
            )
            return list(map(float, emb.tolist()[0]))
        except EmbeddingError:
            raise
        except Exception as exc:  # noqa: BLE001 - surface as EmbeddingError
            logger.warning("SentenceTransformer query embed failed: %s", exc)
            raise EmbeddingError("sentence-transformers query embedding failed", detail=str(exc))
