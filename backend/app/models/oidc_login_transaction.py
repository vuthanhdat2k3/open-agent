from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, gen_id, utc_now


class OidcLoginTransaction(Base):
    __tablename__ = "oidc_login_transactions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_id)
    state_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    nonce_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    code_verifier: Mapped[str] = mapped_column(String(128), nullable=False)
    organization_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    redirect_uri: Mapped[str] = mapped_column(String(512), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)
