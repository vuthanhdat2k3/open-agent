"""OpenAI embeddings embedder (OpenAI-compatible async client)."""

from __future__ import annotations

from typing import Any

from rag_service.config import settings
from rag_service.core.logging import logger
from rag_service.exceptions import EmbeddingError
from rag_service.pipeline.embedder.base import BaseEmbedder


class OpenAIEmbedder(BaseEmbedder):
    def __init__(self, **_: Any) -> None:
        from openai import AsyncOpenAI

        self.client = AsyncOpenAI(
            api_key=settings.openai_key_effective,
            base_url=settings.openai_base_url,
        )
        self.model = settings.openai_embed_model
        self.dimensions = settings.openai_embed_dimensions

    async def _embed(self, texts: list[str]) -> list[list[float]]:
        try:
            out: list[list[float]] = []
            batch_size = max(1, settings.openai_embed_batch_size)
            for i in range(0, len(texts), batch_size):
                batch = texts[i : i + batch_size]
                resp = await self.client.embeddings.create(
                    model=self.model,
                    input=batch,
                    dimensions=self.dimensions,
                )
                out.extend([list(d.embedding) for d in resp.data])
            return out
        except Exception as exc:  # noqa: BLE001 - surface as EmbeddingError
            logger.warning("OpenAI embed call failed: %s", exc)
            raise EmbeddingError("OpenAI embedding failed", detail=str(exc))

    async def _embed_query(self, text: str) -> list[float]:
        try:
            resp = await self.client.embeddings.create(
                model=self.model,
                input=[text],
                dimensions=self.dimensions,
            )
            return list(resp.data[0].embedding)
        except Exception as exc:  # noqa: BLE001 - surface as EmbeddingError
            logger.warning("OpenAI query embed call failed: %s", exc)
            raise EmbeddingError("OpenAI query embedding failed", detail=str(exc))
