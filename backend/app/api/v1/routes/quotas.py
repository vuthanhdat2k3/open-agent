from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.observability.audit import log_action
from app.core.quota.dependencies import _redis_client
from app.db.session import get_db
from app.dependencies import get_current_org_id, require_permission
from app.schemas.quota import (
    OrganizationQuotaOut,
    OrganizationQuotaUpdate,
    QuotaUsageOut,
)
from app.services.quota_service import QuotaService

router = APIRouter(prefix="/api/orgs", tags=["quotas"])


def _ensure_path_org(path_org_id: str, current_org_id: str) -> None:
    if path_org_id != current_org_id:
        raise HTTPException(404, "organization quota not found")


@router.get(
    "/{id}/quota",
    response_model=OrganizationQuotaOut,
    dependencies=[Depends(require_permission("quota:read"))],
)
async def get_quota(
    id: str,
    org_id: str = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
):
    _ensure_path_org(id, org_id)
    quota = await QuotaService(db).get(org_id)
    if quota is None:
        raise HTTPException(404, "organization quota not found")
    return quota


@router.put(
    "/{id}/quota",
    response_model=OrganizationQuotaOut,
    dependencies=[Depends(require_permission("quota:manage"))],
)
async def update_quota(
    id: str,
    body: OrganizationQuotaUpdate,
    request: Request,
    org_id: str = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(_redis_client),
):
    _ensure_path_org(id, org_id)
    quota = await QuotaService(db, redis).update(
        org_id,
        body.model_dump(exclude_unset=True),
        getattr(request.state, "user_id", None),
    )
    await log_action(
        db,
        org_id=org_id,
        actor_user_id=getattr(request.state, "user_id", None),
        action="organization.quota.updated",
        resource_type="organization_quota",
        resource_id=org_id,
        metadata=body.model_dump(exclude_unset=True),
    )
    return quota


@router.get(
    "/{id}/quota/usage",
    response_model=QuotaUsageOut,
    dependencies=[Depends(require_permission("quota:usage"))],
)
async def get_quota_usage(
    id: str,
    org_id: str = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(_redis_client),
):
    _ensure_path_org(id, org_id)
    try:
        return await QuotaService(db, redis).usage(org_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
