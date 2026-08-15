from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from app.core.authz.policy import PrincipalContext

_AUTHORIZATION_CONTEXT = "authorization_context"


def set_ownership_scope(db: AsyncSession, *, principal: PrincipalContext) -> None:
    """Attach the resolved authorization context to this request's DB session."""
    db.info[_AUTHORIZATION_CONTEXT] = principal


def ownership_user_id(db: AsyncSession) -> str | None:
    principal = db.info.get(_AUTHORIZATION_CONTEXT)
    return principal.owner_user_id if principal else None


def scope_to_owner(stmt: Select, db: AsyncSession, owner_column: Any) -> Select:
    user_id = ownership_user_id(db)
    return stmt.where(owner_column == user_id) if user_id else stmt
