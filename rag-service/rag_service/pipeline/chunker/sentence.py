"""Sentence-based chunker.

Splits text into sentences (NLTK ``sent_tokenize`` with a regex fallback), then
greedily packs sentences into chunks. ``chunk_overlap`` is interpreted as the
number of overlapping sentences carried from one chunk into the next.
"""

from __future__ import annotations

import re
from typing import Any

from rag_service.core.logging import logger
from rag_service.pipeline.chunker.base import Chunker, make_chunk

_FALLBACK_SPLIT = re.compile(r"(?<=[.!?])\s+")


def _fallback_sentences(text: str) -> list[str]:
    parts = _FALLBACK_SPLIT.split(text)
    return [p.strip() for p in parts if p.strip()]


class SentenceChunker(Chunker):
    def __init__(
        self,
        chunk_size: int = 800,
        chunk_overlap: int = 150,
        **_: Any,
    ) -> None:
        super().__init__(chunk_size=chunk_size, chunk_overlap=chunk_overlap)

    def _sentences(self, text: str) -> list[str]:
        try:  # pragma: no cover - depends on optional nltk
            import nltk

            try:
                nltk.data.find("tokenizers/punkt")
            except LookupError:
                nltk.download("punkt", quiet=True)
            return [s.strip() for s in nltk.sent_tokenize(text) if s.strip()]
        except Exception as exc:  # pragma: no cover - nltk absent
            logger.warning("nltk unavailable for sentence chunking; using regex fallback: %s", exc)
            return _fallback_sentences(text)

    def chunk(self, text: str, doc_metadata: dict, **kwargs: Any) -> list[TextChunk]:
        if not text:
            return []
        sentences = self._sentences(text)

        # Map each sentence back to its offset in the original text so chunks
        # keep accurate start_char / end_char.
        offsets: list[int] = []
        pos = 0
        for s in sentences:
            idx = text.find(s, pos)
            if idx < 0:
                idx = pos
            offsets.append(idx)
            pos = idx + len(s)

        groups: list[list[int]] = []
        cur: list[int] = []
        cur_len = 0
        for idx, s in enumerate(sentences):
            if cur and cur_len + len(s) > self.chunk_size:
                groups.append(cur)
                cur = []
                cur_len = 0
            cur.append(idx)
            cur_len += len(s)
        if cur:
            groups.append(cur)

        out: list[TextChunk] = []
        prev_end = 0
        for gi, grp in enumerate(groups):
            base = offsets[grp[0]]
            end = offsets[grp[-1]] + len(sentences[grp[-1]])
            if gi == 0:
                start = base
            else:
                # Overlap is expressed in number of sentences; carry the last
                # ``chunk_overlap`` sentences of the previous chunk forward.
                start = max(0, prev_end - self.chunk_overlap_span(prev_end, sentences, offsets))
            chunk_text = text[start:end]
            out.append(make_chunk(chunk_text, len(out), start, end, dict(doc_metadata)))
            prev_end = end

        return out

    def chunk_overlap_span(
        self, prev_end: int, sentences: list[str], offsets: list[int]
    ) -> int:
        """Number of characters of overlap = sum of lengths of the last
        ``chunk_overlap`` sentences that ended at or before ``prev_end``."""
        n = int(self.chunk_overlap)
        if n <= 0:
            return 0
        span = 0
        count = 0
        for i in range(len(sentences) - 1, -1, -1):
            if offsets[i] >= prev_end:
                continue
            span += len(sentences[i])
            count += 1
            if count >= n:
                break
        return span
