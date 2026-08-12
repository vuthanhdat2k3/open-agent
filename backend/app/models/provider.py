import os
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, gen_id, utc_now

if TYPE_CHECKING:
    from app.models.model import Model


class Provider(Base):
    __tablename__ = "providers"
    __table_args__ = (
        UniqueConstraint("org_id", "key", name="uq_providers_org_key"),
        UniqueConstraint("org_id", "name", name="uq_providers_org_name"),
        Index(
            "uq_providers_org_template_baseurl",
            "org_id",
            "template_key",
            "normalized_base_url",
            unique=True,
            sqlite_where=text("template_key IS NOT NULL"),
            postgresql_where=text("template_key IS NOT NULL"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    org_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    base_url: Mapped[str] = mapped_column(String(512), nullable=False)
    normalized_base_url: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    # Legacy plaintext column is retained only for migration/backward-compatible
    # fixtures. New service writes use api_key_encrypted.
    api_key: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    api_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    api_key_last4: Mapped[str | None] = mapped_column(String(8), nullable=True)
    env_var: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    template_key: Mapped[str | None] = mapped_column(String(32), nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(16), default="ready", nullable=False)
    discovery_status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    discovery_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    models_discovered: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    discovery_generation: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    last_discovery_attempt_at: Mapped["utc_now"] = mapped_column(DateTime, nullable=True)
    last_successful_discovery_at: Mapped["utc_now"] = mapped_column(DateTime, nullable=True)
    created_at: Mapped["utc_now"] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped["utc_now"] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)

    models: Mapped[list["Model"]] = relationship(
        back_populates="provider", cascade="all, delete-orphan"
    )

    @property
    def api_key_configured(self) -> bool:
        return bool(
            self.api_key_encrypted
            or self.api_key
            or (self.env_var and os.environ.get(self.env_var))
        )
