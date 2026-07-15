"""Recursive character chunker (LangChain-style recursive split).

Splits text by a priority list of separators, recursing into smaller pieces
until they fit ``chunk_size`` chars, then greedily packs pieces into groups and
slides a window with ``chunk_overlap`` overlap between consecutive chunks.

``start_char`` / ``end_char`` are exact offsets into the ORIGINAL text: every
produced chunk is a contiguous substring ``text[start:end]``.
"""

from __future__ import annotations

from typing import Any

from rag_service.pipeline.chunker.base import Chunker, make_chunk


class RecursiveCharacterChunker(Chunker):
    def __init__(
        self,
        chunk_size: int = 800,
        chunk_overlap: int = 150,
        separators: list[str] | None = None,
        keep_separator: bool = True,
        **_: Any,
    ) -> None:
        super().__init__(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        self.separators = separators or ["\n\n", "\n", ". ", ", ", " ", ""]
        self.keep_separator = keep_separator

    # -- internal recursive split ------------------------------------------ #
    def _split(self, text: str, seps: list[str]) -> list[str]:
        if not text:
            return []
        if len(text) <= self.chunk_size or not seps:
            # Already small enough, or no separators left -> hard cut.
            return [text[i : i + self.chunk_size] for i in range(0, len(text), self.chunk_size)]
        sep = seps[0]
        rest = seps[1:]
        if sep == "":
            return [text[i : i + self.chunk_size] for i in range(0, len(text), self.chunk_size)]
        parts = text.split(sep)
        if len(parts) == 1:
            # Separator absent -> try the next one.
            return self._split(text, rest)
        pieces: list[str] = []
        for i, part in enumerate(parts):
            if self.keep_separator and i < len(parts) - 1:
                part = part + sep
            if len(part) > self.chunk_size and sep != "":
                pieces.extend(self._split(part, rest))
            else:
                pieces.append(part)
        return pieces

    # -- public API -------------------------------------------------------- #
    def chunk(self, text: str, doc_metadata: dict, **kwargs: Any) -> list[TextChunk]:
        if not text:
            return []
        pieces = [p for p in self._split(text, list(self.separators)) if p]

        # Offsets of each leaf piece in the original text. The concatenation of
        # the (separator-appended) pieces reconstructs ``text`` exactly, so the
        # running length equals the true offset.
        offsets: list[int] = []
        pos = 0
        for p in pieces:
            offsets.append(pos)
            pos += len(p)

        # Greedily pack pieces into contiguous groups that fit chunk_size.
        groups: list[list[int]] = []
        cur: list[int] = []
        cur_len = 0
        for idx, p in enumerate(pieces):
            if cur and cur_len + len(p) > self.chunk_size:
                groups.append(cur)
                cur = []
                cur_len = 0
            cur.append(idx)
            cur_len += len(p)
        if cur:
            groups.append(cur)

        # Slide a window across groups, carrying an overlap tail from the
        # previous chunk. Each chunk is text[start:end] -> exact offsets.
        out: list[TextChunk] = []
        prev_end = 0
        for gi, grp in enumerate(groups):
            base = offsets[grp[0]]
            end = offsets[grp[-1]] + len(pieces[grp[-1]])
            if gi == 0:
                start = base
            else:
                start = max(0, prev_end - self.chunk_overlap)
            chunk_text = text[start:end]
            out.append(make_chunk(chunk_text, len(out), start, end, dict(doc_metadata)))
            prev_end = end

        return out
