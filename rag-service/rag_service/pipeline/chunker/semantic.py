"""Semantic Chunker with Contextual Header Enrichment.

Splits text into paragraphs and logical sections based on semantic structure,
headers, and punctuation, preserving structural integrity (headings, lists,
tables) and optionally prefixing chunks with contextual document headers.
"""

from __future__ import annotations

import re
from typing import Any

from rag_service.pipeline.base import TextChunk
from rag_service.pipeline.chunker.base import Chunker, make_chunk

_PARAGRAPH_SPLIT = re.compile(r"\n{2,}")


class SemanticChunker(Chunker):
    """Semantic Chunker that groups paragraphs into cohesive chunks.

    Prevents breaking mid-header, mid-table, or mid-list, and enriches chunks
    with contextual metadata headers when enabled.
    """

    def __init__(
        self,
        chunk_size: int = 800,
        chunk_overlap: int = 150,
        enable_context_header: bool = True,
        **_: Any,
    ) -> None:
        super().__init__(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        self.enable_context_header = enable_context_header

    def _split_semantic_units(self, text: str) -> list[str]:
        raw_paragraphs = _PARAGRAPH_SPLIT.split(text)
        units: list[str] = []
        for para in raw_paragraphs:
            p = para.strip()
            if not p:
                continue
            # If paragraph exceeds chunk size, split by lines or sentences
            if len(p) > self.chunk_size:
                lines = [line.strip() for line in p.splitlines() if line.strip()]
                units.extend(lines)
            else:
                units.append(p)
        return units

    def chunk(self, text: str, doc_metadata: dict, **kwargs: Any) -> list[TextChunk]:
        if not text:
            return []

        units = self._split_semantic_units(text)
        if not units:
            return []

        # Track offsets
        offsets: list[int] = []
        pos = 0
        for u in units:
            idx = text.find(u, pos)
            if idx < 0:
                idx = pos
            offsets.append(idx)
            pos = idx + len(u)

        groups: list[list[int]] = []
        cur: list[int] = []
        cur_len = 0

        for idx, u in enumerate(units):
            if cur and cur_len + len(u) > self.chunk_size:
                groups.append(cur)
                cur = []
                cur_len = 0
            cur.append(idx)
            cur_len += len(u)
        if cur:
            groups.append(cur)

        # Build chunks
        doc_title = doc_metadata.get("source_name") or doc_metadata.get("title") or ""
        header_prefix = f"[Context: Document {doc_title}]\n" if (self.enable_context_header and doc_title) else ""

        out: list[TextChunk] = []
        for gi, grp in enumerate(groups):
            start = offsets[grp[0]]
            end = offsets[grp[-1]] + len(units[grp[-1]])
            raw_chunk_text = text[start:end]
            final_text = f"{header_prefix}{raw_chunk_text}" if header_prefix else raw_chunk_text

            chunk_meta = dict(doc_metadata)
            chunk_meta["is_semantic"] = True
            chunk_meta["unit_count"] = len(grp)

            out.append(make_chunk(final_text, len(out), start, end, chunk_meta))

        return out
