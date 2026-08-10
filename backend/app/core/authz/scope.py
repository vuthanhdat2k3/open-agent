from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

_OWNERSHIP_USER_ID = "ownership_user_id"


def set_ownership_scope(db: AsyncSession, *, user_id: str, role: Any) -> None:
    """Scope subsequent reads on this request session for plain users."""
    role_value = getattr(role, "value", role)
    db.info[_OWNERSHIP_USER_ID] = user_id if role_value == "user" else None


def ownership_user_id(db: AsyncSession) -> str | None:
    return db.info.get(_OWNERSHIP_USER_ID)


def scope_to_owner(stmt: Select, db: AsyncSession, owner_column: Any) -> Select:
    user_id = ownership_user_id(db)
    return stmt.where(owner_column == user_id) if user_id else stmt
