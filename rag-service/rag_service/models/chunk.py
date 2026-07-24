"""Chunk ORM model — a text segment of a document."""

from __future__ import annotations

import json
from datetime import datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from rag_service.db.base import Base

if TYPE_CHECKING:
    from rag_service.models.document import Document


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[str] = mapped_column(
        Text, primary_key=True, default=lambda: f"chunk_{uuid4().hex[:8]}"
    )
    document_id: Mapped[str] = mapped_column(
        Text, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    collection_id: Mapped[str] = mapped_column(Text, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    start_char: Mapped[int] = mapped_column(Integer, default=0)
    end_char: Mapped[int] = mapped_column(Integer, default=0)
    token_count: Mapped[int] = mapped_column(Integer, default=0)

    _metadata: Mapped[str] = mapped_column("chunk_metadata", Text, default="{}")

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow
    )

    document: Mapped["Document"] = relationship(back_populates="chunks")

    @property
    def chunk_metadata(self) -> dict:
        return json.loads(self._metadata)

    @chunk_metadata.setter
    def chunk_metadata(self, value: dict) -> None:
        self._metadata = json.dumps(value or {})
