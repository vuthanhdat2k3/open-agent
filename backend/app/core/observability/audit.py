from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog


async def log_action(
    db: AsyncSession,
    *,
    org_id: str,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    actor_user_id: str | None = None,
    actor_api_key_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    ip: str | None = None,
    commit: bool = True,
) -> None:
    """Append one audit row.

    ``commit=False`` leaves the flush to the surrounding transaction. The
    agent loop audits every tool call and guardrail decision, so committing
    inside each call would mean a database round trip per tool — and would
    also tear the caller's transaction boundary mid-run.
    """
    db.add(
        AuditLog(
            org_id=org_id,
            actor_user_id=actor_user_id,
            actor_api_key_id=actor_api_key_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            metadata_=metadata or {},
            ip=ip,
        )
    )
    if commit:
        await db.commit()

