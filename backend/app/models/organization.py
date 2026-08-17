from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, gen_id, utc_now

if TYPE_CHECKING:
    from app.models.api_key import ApiKey
    from app.models.membership import Membership


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    slug: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    zitadel_org_id: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True, index=True)
    lifecycle_status: Mapped[str] = mapped_column(String(24), nullable=False, default="active")
    provisioning_mode: Mapped[str] = mapped_column(String(24), nullable=False, default="managed")
    created_at: Mapped[utc_now] = mapped_column(DateTime, default=utc_now)

    memberships: Mapped[list[Membership]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )
    api_keys: Mapped[list[ApiKey]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )
