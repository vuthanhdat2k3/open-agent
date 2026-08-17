from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, gen_id, utc_now

if TYPE_CHECKING:
    from app.models.membership import Membership
    from app.models.organization import Organization
    from app.models.user import User


class ApplicationSession(Base):
    """Opaque BFF session; browser tokens are never persisted in the database."""

    __tablename__ = "application_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    session_token_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    csrf_token_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    membership_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("memberships.id", ondelete="CASCADE"), nullable=False, index=True
    )
    zitadel_session_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    auth_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)
    idle_expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    absolute_expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    revocation_reason: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_ip_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_user_agent_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)

    user: Mapped[User] = relationship()
    organization: Mapped[Organization] = relationship()
    membership: Mapped[Membership] = relationship()
