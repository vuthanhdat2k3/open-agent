"""Local, dependency-free hashed bag-of-words embedder.

Deterministic and always works offline: hashes each lowercased token into a
fixed-dimensional vector, accumulates counts and L2-normalizes. Cosine-friendly.
"""

from __future__ import annotations

import hashlib
import math
import re
from typing import Any

from rag_service.pipeline.embedder.base import BaseEmbedder

_DIM = 512
_STOPWORDS = frozenset(
    {
        "a", "an", "the", "and", "or", "but", "if", "then", "else", "of", "to",
        "in", "on", "at", "by", "for", "with", "as", "is", "are", "was", "were",
        "be", "been", "being", "this", "that", "these", "those", "it", "its",
        "from", "into", "about", "over", "than", "so", "not", "no", "yes",
    }
)
_TOKEN_RE = re.compile(r"[a-z0-9]+")


class SimpleEmbedder(BaseEmbedder):
    def __init__(self, **_: Any) -> None:
        self.model = "simple-hash"
        self.dimensions = _DIM

    def _vec(self, text: str) -> list[float]:
        vec = [0.0] * _DIM
        if not text:
            return vec
        for tok in _TOKEN_RE.findall(text.lower()):
            if tok in _STOPWORDS:
                continue
            digest = hashlib.md5(tok.encode("utf-8")).digest()[:8]
            idx = int.from_bytes(digest, "big") % _DIM
            vec[idx] += 1.0
        norm = math.sqrt(sum(x * x for x in vec))
        if norm > 0.0:
            vec = [x / norm for x in vec]
        return vec

    async def _embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]

    async def _embed_query(self, text: str) -> list[float]:
        return self._vec(text)
