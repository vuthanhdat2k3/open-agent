from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, gen_id, utc_now

if TYPE_CHECKING:
    from app.models.provider import Provider



class Model(Base):
    __tablename__ = "models"
    __table_args__ = (
        UniqueConstraint("provider_id", "name", name="uq_models_provider_name"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    provider_id: Mapped[str] = mapped_column(
        ForeignKey("providers.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    tier: Mapped[str] = mapped_column(String(32), default="balanced", nullable=False)
    context_window: Mapped[int] = mapped_column(Integer, default=8192, nullable=False)
    input_cost_per_1k: Mapped[float] = mapped_column(Float, default=0.0)
    output_cost_per_1k: Mapped[float] = mapped_column(Float, default=0.0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped["utc_now"] = mapped_column(DateTime, default=utc_now)

    provider: Mapped["Provider"] = relationship(back_populates="models")
