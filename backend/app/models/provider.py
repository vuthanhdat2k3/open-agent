from sqlalchemy import Boolean, DateTime, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, gen_id, utc_now


class Provider(Base):
    __tablename__ = "providers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    base_url: Mapped[str] = mapped_column(String(512), nullable=False)
    api_key: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    env_var: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped["utc_now"] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped["utc_now"] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now
    )

    models: Mapped[list["Model"]] = relationship(
        back_populates="provider", cascade="all, delete-orphan"
    )
