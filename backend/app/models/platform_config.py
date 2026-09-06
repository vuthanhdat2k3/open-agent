from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, utc_now


class PlatformConfig(Base):
    """A DB-backed override for one allow-listed, instance-wide Settings
    field (see app/core/platform_config_schema.py for the allow-list).

    Deliberately not org-scoped: this is instance-level operational config
    (optional integration API keys, observability/sandbox tuning) editable
    by platform_admin, layered on top of the .env-sourced Settings default.
    Core auth/DB/session secrets are never allow-listed here — see the
    schema module's docstring for why.
    """

    __tablename__ = "platform_config"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False, default="")
    updated_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)
