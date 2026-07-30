"""Parent-Child Hierarchical Chunker.

Creates small 'child' chunks for dense vector matching while attaching the ID
and text of larger 'parent' chunks in metadata for full-context synthesis.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from rag_service.pipeline.base import TextChunk
from rag_service.pipeline.chunker.base import Chunker, make_chunk
from rag_service.pipeline.chunker.recursive import RecursiveCharacterChunker


class ParentChildChunker(Chunker):
    """Hierarchical Chunker that creates small child chunks linked to larger parent chunks."""

    def __init__(
        self,
        parent_chunk_size: int = 1500,
        child_chunk_size: int = 300,
        chunk_overlap: int = 50,
        **_: Any,
    ) -> None:
        super().__init__(chunk_size=child_chunk_size, chunk_overlap=chunk_overlap)
        self.parent_chunker = RecursiveCharacterChunker(
            chunk_size=parent_chunk_size, chunk_overlap=chunk_overlap * 2
        )
        self.child_chunker = RecursiveCharacterChunker(
            chunk_size=child_chunk_size, chunk_overlap=chunk_overlap
        )

    def chunk(self, text: str, doc_metadata: dict, **kwargs: Any) -> list[TextChunk]:
        if not text:
            return []

        parents = self.parent_chunker.chunk(text, doc_metadata, **kwargs)
        all_children: list[TextChunk] = []

        for p_idx, parent in enumerate(parents):
            parent_id = f"parent_{uuid4().hex[:8]}"
            parent_text = parent.text

            # Chunk the parent text into smaller child chunks
            children = self.child_chunker.chunk(parent_text, doc_metadata, **kwargs)
            for c_idx, child in enumerate(children):
                child_meta = dict(child.metadata)
                child_meta["parent_id"] = parent_id
                child_meta["parent_chunk_index"] = p_idx
                child_meta["parent_text"] = parent_text
                child_meta["is_child"] = True

                # Start and end chars relative to original document
                abs_start = parent.start_char + child.start_char
                abs_end = parent.start_char + child.end_char

                all_children.append(
                    make_chunk(
                        text=child.text,
                        index=len(all_children),
                        start=abs_start,
                        end=abs_end,
                        metadata=child_meta,
                    )
                )

        return all_children
