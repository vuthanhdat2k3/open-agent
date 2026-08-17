from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.api_key import generate_api_key
from app.core.observability.audit import log_action
from app.db.base import utc_now
from app.db.session import get_db
from app.dependencies import get_current_user, require_permission
from app.models.api_key import ApiKey
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.role import Role
from app.models.user import User
from app.schemas.auth import (
    ApiKeyCreateRequest,
    ApiKeyCreateResponse,
    ApiKeyOut,
    InviteMemberRequest,
)
from app.services.quota_service import default_organization_quota

router = APIRouter(prefix="/api/orgs", tags=["orgs"])


class OrgCreateRequest(BaseModel):
    name: str


class OrgOut(BaseModel):
    id: str
    name: str
    slug: str
    created_at: datetime


class OrgMemberOut(BaseModel):
    user_id: str
    email: str
    display_name: str
    role: str
    created_at: datetime


def _public_role(role: Role) -> str:
    return "admin" if role == Role.org_admin else role.value


async def _ensure_user_belongs_to_org(
    db: AsyncSession, user_id: str, org_id: str
) -> Membership:
    res = await db.execute(
        select(Membership).where(Membership.org_id == org_id, Membership.user_id == user_id)
    )
    membership = res.scalar_one_or_none()
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User does not belong to this organization",
        )
    return membership


@router.post("", response_model=OrgOut, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_permission("orgs:create"))])
async def create_org(
    body: OrgCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    slug = f"{body.name.lower().replace(' ', '-')}-{str(uuid.uuid4())[:8]}"
    org = Organization(name=body.name, slug=slug)
    db.add(org)
    await db.flush()
    db.add(default_organization_quota(org.id))

    membership = Membership(org_id=org.id, user_id=current_user.id, role=Role.org_admin)
    db.add(membership)
    await db.commit()
    await db.refresh(org)
    return OrgOut(id=org.id, name=org.name, slug=org.slug, created_at=org.created_at)


@router.get("/{id}/members", response_model=list[OrgMemberOut], dependencies=[Depends(require_permission("orgs:read"))])
async def list_org_members(
    id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _ensure_user_belongs_to_org(db, current_user.id, id)
    res = await db.execute(
        select(Membership, User)
        .join(User, Membership.user_id == User.id)
        .where(Membership.org_id == id)
    )
    rows = res.all()
    return [
        OrgMemberOut(
            user_id=u.id,
            email=u.email,
            display_name=u.display_name,
            role=_public_role(mem.role),
            created_at=mem.created_at,
        )
        for mem, u in rows
    ]


@router.post("/{id}/members", response_model=OrgMemberOut, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_permission("orgs:manage"))])
async def add_org_member(
    id: str,
    body: InviteMemberRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _ensure_user_belongs_to_org(db, current_user.id, id)
    res_u = await db.execute(select(User).where(User.email == body.email.lower()))
    invited_user = res_u.scalar_one_or_none()
    if not invited_user:
        raise HTTPException(
            404, "User with this email not found. Invite requires registered User."
        )

    res_mem = await db.execute(
        select(Membership).where(Membership.org_id == id, Membership.user_id == invited_user.id)
    )
    if res_mem.scalar_one_or_none():
        raise HTTPException(400, "User is already a member of this organization")

    role_val = {
        "admin": Role.org_admin,
        "org_admin": Role.org_admin,
        "operator": Role.operator,
        "user": Role.user,
    }.get(body.role, Role.user)
    mem = Membership(
        org_id=id,
        user_id=invited_user.id,
        role=role_val,
        invited_by_user_id=current_user.id,
    )
    db.add(mem)
    await db.commit()
    await db.refresh(mem)
    await log_action(
        db,
        org_id=id,
        actor_user_id=current_user.id,
        action="membership.added",
        resource_type="membership",
        resource_id=mem.id,
        metadata={"user_id": invited_user.id, "role": str(mem.role)},
    )

    return OrgMemberOut(
        user_id=invited_user.id,
        email=invited_user.email,
        display_name=invited_user.display_name,
        role=_public_role(mem.role),
        created_at=mem.created_at,
    )


@router.delete("/{id}/members/{user_id}", dependencies=[Depends(require_permission("orgs:manage"))])
async def remove_org_member(
    id: str,
    user_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _ensure_user_belongs_to_org(db, current_user.id, id)
    res_mem = await db.execute(
        select(Membership).where(Membership.org_id == id, Membership.user_id == user_id)
    )
    mem = res_mem.scalar_one_or_none()
    if not mem:
        raise HTTPException(404, "Member not found in organization")

    await db.delete(mem)
    await db.commit()
    await log_action(
        db,
        org_id=id,
        actor_user_id=current_user.id,
        action="membership.removed",
        resource_type="membership",
        resource_id=user_id,
    )
    return {"ok": True}


@router.post("/{id}/api-keys", response_model=ApiKeyCreateResponse, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_permission("orgs:manage"))])
async def create_api_key_endpoint(
    id: str,
    body: ApiKeyCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _ensure_user_belongs_to_org(db, current_user.id, id)
    full_key, key_prefix, key_hash = generate_api_key()
    expires_at = None
    if body.expires_days:
        expires_at = utc_now() + timedelta(days=body.expires_days)

    api_key_obj = ApiKey(
        org_id=id,
        created_by_user_id=current_user.id,
        name=body.name,
        key_prefix=key_prefix,
        key_hash=key_hash,
        expires_at=expires_at,
    )
    db.add(api_key_obj)
    await db.commit()
    await db.refresh(api_key_obj)
    await log_action(
        db,
        org_id=id,
        actor_user_id=current_user.id,
        action="api_key.created",
        resource_type="api_key",
        resource_id=api_key_obj.id,
        metadata={"name": api_key_obj.name, "key_prefix": api_key_obj.key_prefix},
    )

    return ApiKeyCreateResponse(
        api_key=ApiKeyOut.model_validate(api_key_obj),
        secret_key=full_key,
    )


@router.get("/{id}/api-keys", response_model=list[ApiKeyOut], dependencies=[Depends(require_permission("orgs:read"))])
async def list_api_keys(
    id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _ensure_user_belongs_to_org(db, current_user.id, id)
    res = await db.execute(
        select(ApiKey)
        .where(ApiKey.org_id == id, ApiKey.revoked_at.is_(None))
        .order_by(ApiKey.created_at.desc())
    )
    return [ApiKeyOut.model_validate(k) for k in res.scalars().all()]


@router.delete("/{id}/api-keys/{key_id}", dependencies=[Depends(require_permission("orgs:manage"))])
async def revoke_api_key(
    id: str,
    key_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _ensure_user_belongs_to_org(db, current_user.id, id)
    res = await db.execute(
        select(ApiKey).where(ApiKey.id == key_id, ApiKey.org_id == id)
    )
    key_obj = res.scalar_one_or_none()
    if not key_obj:
        raise HTTPException(404, "API key not found")

    key_obj.revoked_at = utc_now()
    await db.commit()
    await log_action(
        db,
        org_id=id,
        actor_user_id=current_user.id,
        action="api_key.revoked",
        resource_type="api_key",
        resource_id=key_obj.id,
        metadata={"name": key_obj.name, "key_prefix": key_obj.key_prefix},
    )
    return {"ok": True}
