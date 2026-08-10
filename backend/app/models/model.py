from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, gen_id, utc_now

if TYPE_CHECKING:
    from app.models.provider import Provider


class Model(Base):
    __tablename__ = "models"
    __table_args__ = (UniqueConstraint("provider_id", "name", name="uq_models_provider_name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    org_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    provider_id: Mapped[str] = mapped_column(ForeignKey("providers.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    tier: Mapped[str] = mapped_column(String(32), default="balanced", nullable=False)
    context_window: Mapped[int] = mapped_column(Integer, default=8192, nullable=False)
    input_cost_per_1k: Mapped[float] = mapped_column(Float, default=0.0)
    output_cost_per_1k: Mapped[float] = mapped_column(Float, default=0.0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    discovered: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_seen_at: Mapped["utc_now"] = mapped_column(DateTime, nullable=True)
    source: Mapped[str] = mapped_column(String(16), default="manual", nullable=False)
    catalog_source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    catalog_version: Mapped[str | None] = mapped_column(String(16), nullable=True)
    last_discovered_at: Mapped["utc_now"] = mapped_column(DateTime, nullable=True)
    supports_tools: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    supports_reasoning: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    supports_vision: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    created_at: Mapped["utc_now"] = mapped_column(DateTime, default=utc_now)

    provider: Mapped["Provider"] = relationship(back_populates="models")
