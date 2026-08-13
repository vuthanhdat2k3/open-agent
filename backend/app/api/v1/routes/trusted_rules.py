from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import gen_id, utc_now
from app.dependencies import get_current_org_id, get_current_user, get_db, require_any_permission, require_permission
from app.models.customer_intelligence import CalendarConnection, CiPublicEmailDomain, CiTrustedRule
from app.models.user import User

router = APIRouter(prefix="/api/email-intelligence/trusted-rules", tags=["trusted-rules"])


class RuleInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=2, max_length=160)
    match_type: Literal["EMAIL", "DOMAIN"]
    match_value: str = Field(min_length=3, max_length=320)
    calendar_connection_id: str = Field(min_length=3, max_length=36)
    minimum_classification_confidence: float = Field(default=0.95, ge=0.95, le=1)
    maximum_events_per_day: int = Field(default=3, ge=1, le=20)
    expires_at: datetime


def _validate_rule(body: RuleInput, public_domains: set[str]) -> None:
    value = body.match_value.strip().lower()
    if value in {"*", "*."} or "*" in value:
        raise HTTPException(422, "Wildcard trusted rules are not allowed")
    if body.match_type == "DOMAIN" and value in public_domains:
        raise HTTPException(422, "Public email provider domains cannot be used for domain-wide rules")
    if body.expires_at <= datetime.now(timezone.utc):
        raise HTTPException(422, "Rule expiry must be in the future")


async def _public_domains(db: AsyncSession) -> set[str]:
    rows = await db.scalars(select(CiPublicEmailDomain.domain).where(CiPublicEmailDomain.enabled.is_(True)))
    return {row.lower() for row in rows}


def _out(row: CiTrustedRule) -> dict:
    return {
        "id": row.id,
        "version": row.version,
        "name": row.name,
        "status": row.status,
        "match": {"type": row.match_type, "value": row.match_value},
        "action": {"type": row.action_type, "calendar_connection_id": row.calendar_connection_id},
        "conditions": row.conditions,
        "policy_version": row.policy_version,
        "capabilities": {"can_edit": row.status == "ACTIVE", "can_disable": row.status == "ACTIVE", "can_delete": False, "blocked_reasons": {}},
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


@router.get("", dependencies=[Depends(require_permission("ci:read"))])
async def list_rules(org_id: str = Depends(get_current_org_id), current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    rows = await db.scalars(select(CiTrustedRule).where(CiTrustedRule.org_id == org_id, CiTrustedRule.created_by_user_id == current_user.id, CiTrustedRule.status != "DELETED").order_by(CiTrustedRule.updated_at.desc()))
    registry_version = await db.scalar(select(CiPublicEmailDomain.registry_version).where(CiPublicEmailDomain.enabled.is_(True)).order_by(CiPublicEmailDomain.updated_at.desc()).limit(1))
    return {"items": [_out(row) for row in rows], "policy": {"max_active_rules_per_user": 10, "max_active_rules_per_org": 200, "max_auto_events_per_user_per_day": 20, "max_auto_events_per_org_per_day": 500, "public_domain_registry_version": registry_version or "unknown"}, "meta": {"server_time": utc_now().isoformat()}}


@router.post("/preview", dependencies=[Depends(require_any_permission("ci:manage", "ci:personal:manage"))])
async def preview_rule(body: RuleInput, org_id: str = Depends(get_current_org_id), db: AsyncSession = Depends(get_db)):
    _validate_rule(body, await _public_domains(db))
    return {"estimated_recent_matches": 0, "sample_matches": [], "policy": {"accepted": True, "warnings": ["Shadow mode: preview không tạo proposal hoặc calendar event."]}, "meta": {"server_time": utc_now().isoformat(), "public_domain_registry_version": "2026-08-13.1"}}


@router.post("", status_code=201, dependencies=[Depends(require_any_permission("ci:manage", "ci:personal:manage"))])
async def create_rule(body: RuleInput, org_id: str = Depends(get_current_org_id), current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _validate_rule(body, await _public_domains(db))
    connection = await db.scalar(select(CalendarConnection).where(CalendarConnection.id == body.calendar_connection_id, CalendarConnection.org_id == org_id))
    if connection is None:
        raise HTTPException(404, "Calendar connection not found in the active organization")
    if connection.status != "connected":
        raise HTTPException(409, "Calendar connection must be connected before creating a trusted rule")
    active_user = await db.scalar(select(func.count(CiTrustedRule.id)).where(CiTrustedRule.org_id == org_id, CiTrustedRule.created_by_user_id == current_user.id, CiTrustedRule.status == "ACTIVE"))
    if int(active_user or 0) >= 10:
        raise HTTPException(409, "Active trusted-rule limit reached")
    active_org = await db.scalar(select(func.count(CiTrustedRule.id)).where(CiTrustedRule.org_id == org_id, CiTrustedRule.status == "ACTIVE"))
    if int(active_org or 0) >= 200:
        raise HTTPException(409, "Organization trusted-rule limit reached")
    row = CiTrustedRule(id=gen_id(), org_id=org_id, created_by_user_id=current_user.id, name=body.name.strip(), match_type=body.match_type, match_value=body.match_value.strip().lower(), calendar_connection_id=body.calendar_connection_id, conditions={"minimum_classification_confidence": body.minimum_classification_confidence, "maximum_events_per_day": body.maximum_events_per_day, "expires_at": body.expires_at.isoformat(), "required_guard_outcome": "PASS", "sender_authentication": "SPF_DKIM_DMARC_ALIGNED"})
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return _out(row)
