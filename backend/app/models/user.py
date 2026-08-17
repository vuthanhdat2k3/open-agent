from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, gen_id, utc_now

if TYPE_CHECKING:
    from app.models.api_key import ApiKey
    from app.models.membership import Membership
    from app.models.oauth_account import OAuthAccount
    from app.models.refresh_token import RefreshToken


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    zitadel_user_id: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True, index=True)
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    lifecycle_status: Mapped[str] = mapped_column(String(24), nullable=False, default="active")
    created_at: Mapped[utc_now] = mapped_column(DateTime, default=utc_now)

    memberships: Mapped[list[Membership]] = relationship(
        back_populates="user", cascade="all, delete-orphan", foreign_keys="Membership.user_id"
    )
    oauth_accounts: Mapped[list[OAuthAccount]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    refresh_tokens: Mapped[list[RefreshToken]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    api_keys: Mapped[list[ApiKey]] = relationship(
        back_populates="created_by_user", foreign_keys="ApiKey.created_by_user_id"
    )
