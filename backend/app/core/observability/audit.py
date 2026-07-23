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
) -> None:
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
    await db.commit()

