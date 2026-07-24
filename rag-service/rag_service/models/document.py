"""Document ORM model — a source (file / URL / text) and its ingest state."""

from __future__ import annotations

import json
from datetime import datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from rag_service.db.base import Base

if TYPE_CHECKING:
    from rag_service.models.chunk import Chunk
    from rag_service.models.collection import Collection


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(
        Text, primary_key=True, default=lambda: f"doc_{uuid4().hex[:8]}"
    )
    collection_id: Mapped[str] = mapped_column(
        Text, ForeignKey("collections.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, default="pending")
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    token_count: Mapped[int] = mapped_column(Integer, default=0)

    # JSON-backed columns (stored as text, surfaced as python objects).
    _tags: Mapped[str] = mapped_column("tags", Text, default="[]")
    _metadata: Mapped[str] = mapped_column("doc_metadata", Text, default="{}")
    _errors: Mapped[str] = mapped_column("ingest_errors", Text, default="[]")

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    collection: Mapped["Collection"] = relationship(back_populates="documents")
    chunks: Mapped[list["Chunk"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )

    # ----- tags ----- #
    @property
    def tags(self) -> list[str]:
        return json.loads(self._tags)

    @tags.setter
    def tags(self, value: list[str]) -> None:
        self._tags = json.dumps(value or [])

    # ----- metadata ----- #
    @property
    def doc_metadata(self) -> dict:
        return json.loads(self._metadata)

    @doc_metadata.setter
    def doc_metadata(self, value: dict) -> None:
        self._metadata = json.dumps(value or {})

    # ----- errors ----- #
    @property
    def ingest_errors(self) -> list[dict]:
        return json.loads(self._errors)

    @ingest_errors.setter
    def ingest_errors(self, value: list[dict]) -> None:
        self._errors = json.dumps(value or [])
