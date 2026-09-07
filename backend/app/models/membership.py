from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, gen_id, utc_now
from app.models.role import Role

if TYPE_CHECKING:
    from app.models.organization import Organization
    from app.models.user import User


class Membership(Base):
    __tablename__ = "memberships"
    # A user may hold more than one role in the same org (e.g. a self-
    # registered founder gets both org_admin and operator) - uniqueness is
    # per role-row, not per (org, user).
    __table_args__ = (UniqueConstraint("org_id", "user_id", "role", name="uq_membership_org_user_role"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    org_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # native_enum=False: this column is a plain VARCHAR in the DB (see
    # migration 0025, which dropped the old Postgres native `role` enum type)
    # - keeps Role's Python-side typing/validation without SQLAlchemy trying
    # to cast values with `::role`, a type that no longer exists.
    role: Mapped[Role] = mapped_column(Enum(Role, native_enum=False, length=32), nullable=False, default=Role.user)
    lifecycle_status: Mapped[str] = mapped_column(String(24), nullable=False, default="active")
    provisioning_source: Mapped[str] = mapped_column(String(24), nullable=False, default="platform")
    zitadel_role_assignment_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    invited_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[utc_now] = mapped_column(DateTime, default=utc_now)

    organization: Mapped[Organization] = relationship(back_populates="memberships")
    user: Mapped[User] = relationship(back_populates="memberships", foreign_keys=[user_id])
    invited_by: Mapped[User | None] = relationship(foreign_keys=[invited_by_user_id])
