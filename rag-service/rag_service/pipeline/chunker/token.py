"""Token-based chunker (tiktoken, with a whitespace-word fallback).

Encodes the text into tokens and slides a window of ``chunk_size`` tokens with
``chunk_overlap`` token overlap, decoding each window back to a string. Token
offsets are mapped back to character offsets in the original text.
"""

from __future__ import annotations

from typing import Any

from rag_service.core.logging import logger
from rag_service.pipeline.base import TextChunk
from rag_service.pipeline.chunker.base import Chunker, make_chunk


class TokenChunker(Chunker):
    def __init__(
        self,
        chunk_size: int = 800,
        chunk_overlap: int = 150,
        encoding_name: str = "cl100k_base",
        **_: Any,
    ) -> None:
        super().__init__(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        self.encoding_name = encoding_name

    def _tokens(self, text: str) -> tuple[list[str], bool]:
        """Return decoded tokens and whether tiktoken was used."""
        try:  # pragma: no cover - depends on optional tiktoken
            import tiktoken

            enc = tiktoken.get_encoding(self.encoding_name)
            tokens = [enc.decode([tid]) for tid in enc.encode(text)]
            return tokens, True
        except Exception as exc:  # pragma: no cover - tiktoken absent
            logger.warning("tiktoken unavailable; approximating tokens by whitespace: %s", exc)
            return text.split(), False

    def chunk(self, text: str, doc_metadata: dict, **kwargs: Any) -> list[TextChunk]:
        if not text:
            return []
        tokens, _ = self._tokens(text)
        if not tokens:
            return []

        # Map each token/word back to its character span in the original text.
        spans: list[tuple[int, int]] = []
        pos = 0
        for tok in tokens:
            idx = text.find(tok, pos)
            if idx < 0:
                idx = pos
            spans.append((idx, idx + len(tok)))
            pos = idx + len(tok)

        step = max(1, self.chunk_size - self.chunk_overlap)
        out: list[TextChunk] = []
        idx = 0
        start_tok = 0
        n = len(tokens)
        while start_tok < n:
            end_tok = min(n, start_tok + self.chunk_size)
            start_char = spans[start_tok][0]
            end_char = spans[end_tok - 1][1]
            chunk_text = text[start_char:end_char]
            out.append(make_chunk(chunk_text, idx, start_char, end_char, dict(doc_metadata)))
            idx += 1
            if end_tok == n:
                break
            start_tok += step

        return out
