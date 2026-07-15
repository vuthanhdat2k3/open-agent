"""Ollama embeddings embedder (local HTTP API)."""

from __future__ import annotations

from typing import Any

from rag_service.config import settings
from rag_service.core.logging import logger
from rag_service.exceptions import EmbeddingError
from rag_service.pipeline.embedder.base import BaseEmbedder


class OllamaEmbedder(BaseEmbedder):
    def __init__(self, **_: Any) -> None:
        self.base_url = settings.ollama_base_url.rstrip("/")
        self.model = settings.ollama_embed_model
        self.dimensions = 0  # discovered on first successful embed

    async def _embed(self, texts: list[str]) -> list[list[float]]:
        import httpx

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{self.base_url}/api/embeddings",
                    json={"model": self.model, "input": texts},
                )
                resp.raise_for_status()
                data = resp.json()
            vectors = data.get("embeddings")
            if not isinstance(vectors, list) or not vectors:
                raise EmbeddingError("Ollama returned no embeddings")
            if self.dimensions == 0 and vectors:
                self.dimensions = len(vectors[0])
            return [list(v) for v in vectors]
        except EmbeddingError:
            raise
        except Exception as exc:  # noqa: BLE001 - surface as EmbeddingError
            logger.warning("Ollama embed call failed: %s", exc)
            raise EmbeddingError("Ollama embedding failed", detail=str(exc))

    async def _embed_query(self, text: str) -> list[float]:
        import httpx

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{self.base_url}/api/embeddings",
                    json={"model": self.model, "input": [text]},
                )
                resp.raise_for_status()
                data = resp.json()
            vectors = data.get("embeddings")
            if not isinstance(vectors, list) or not vectors:
                raise EmbeddingError("Ollama returned no embeddings")
            if self.dimensions == 0:
                self.dimensions = len(vectors[0])
            return list(vectors[0])
        except EmbeddingError:
            raise
        except Exception as exc:  # noqa: BLE001 - surface as EmbeddingError
            logger.warning("Ollama query embed call failed: %s", exc)
            raise EmbeddingError("Ollama query embedding failed", detail=str(exc))
