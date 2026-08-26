from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.auth.api_key import generate_api_key
from app.core.auth.password import hash_password
from app.core.observability.audit import log_action
from app.db.base import utc_now
from app.db.session import get_db
from app.dependencies import get_current_user, require_permission
from app.models.api_key import ApiKey
from app.models.application_session import ApplicationSession
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
from app.services.zitadel_service import ZitadelProvisioningService

router = APIRouter(prefix="/api/orgs", tags=["orgs"])


class OrgCreateRequest(BaseModel):
    name: str
    admin_email: str | None = None
    initial_password: str | None = None


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
    if get_settings().auth_provider == "local" and role == Role.org_admin:
        return "admin"
    return role.value


async def _is_platform_admin(db: AsyncSession, user_id: str) -> bool:
    result = await db.execute(
        select(Membership).join(Organization, Membership.org_id == Organization.id).where(
            Membership.user_id == user_id,
            Membership.role == Role.platform_admin,
            Membership.lifecycle_status == "active",
        )
    )
    return result.scalar_one_or_none() is not None


async def _ensure_user_belongs_to_org(
    db: AsyncSession, user_id: str, org_id: str
) -> Membership | None:
    if await _is_platform_admin(db, user_id):
        return None
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


async def require_platform_admin(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Authorize instance-level organization provisioning without an active org."""
    if get_settings().auth_provider == "local":
        return current_user
    result = await db.execute(
        select(Membership).join(Organization, Membership.org_id == Organization.id).where(
            Membership.user_id == current_user.id,
            Organization.slug == "platform",
            Membership.role == Role.platform_admin,
            Membership.lifecycle_status == "active",
        )
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only platform_admin can create organizations")
    return current_user


@router.post("", response_model=OrgOut, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_platform_admin)])
async def create_org(
    body: OrgCreateRequest,
    current_user: User = Depends(require_platform_admin),
    db: AsyncSession = Depends(get_db),
):
    if get_settings().auth_provider == "zitadel":
        # require_platform_admin already validates the instance-level
        # platform organization by slug; its database id is not stable.
        pass
    slug = f"{body.name.lower().replace(' ', '-')}-{str(uuid.uuid4())[:8]}"
    org = Organization(name=body.name, slug=slug)
    db.add(org)
    await db.flush()
    db.add(default_organization_quota(org.id))

    membership = Membership(org_id=org.id, user_id=current_user.id, role=Role.org_admin)
    db.add(membership)

    if body.admin_email and body.admin_email.strip().lower() != (current_user.email or "").lower():
        target_email = body.admin_email.strip().lower()
        initial_pass = body.initial_password or "OpenAgent@2026"
        res_u = await db.execute(select(User).where(User.email == target_email))
        target_user = res_u.scalar_one_or_none()
        if not target_user:
            target_user = User(
                email=target_email,
                display_name=target_email.split("@", 1)[0],
                hashed_password=hash_password(initial_pass),
            )
            db.add(target_user)
            await db.flush()
        elif not target_user.hashed_password:
            target_user.hashed_password = hash_password(initial_pass)
            await db.flush()
        invited_membership = Membership(
            org_id=org.id,
            user_id=target_user.id,
            role=Role.org_admin,
            invited_by_user_id=current_user.id,
            provisioning_source="invite",
        )
        db.add(invited_membership)

        await ZitadelProvisioningService().provision_user(
            email=target_email,
            display_name=target_user.display_name,
            initial_password=initial_pass,
        )

    await db.commit()
    await db.refresh(org)
    return OrgOut(id=org.id, name=org.name, slug=org.slug, created_at=org.created_at)


@router.get("", response_model=list[OrgOut], dependencies=[Depends(require_permission("orgs:read"))])
async def list_orgs(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Platform admins see all tenants; other roles see only their memberships."""
    membership_query = select(Membership).where(
        Membership.user_id == current_user.id,
        Membership.lifecycle_status == "active",
    )
    memberships = (await db.execute(membership_query)).scalars().all()
    if any(mem.role == Role.platform_admin for mem in memberships):
        result = await db.execute(select(Organization).order_by(Organization.created_at.desc()))
        organizations = result.scalars().all()
    else:
        org_ids = [mem.org_id for mem in memberships]
        result = await db.execute(
            select(Organization).where(Organization.id.in_(org_ids)).order_by(Organization.created_at.desc())
        )
        organizations = result.scalars().all()
    return [OrgOut(id=org.id, name=org.name, slug=org.slug, created_at=org.created_at) for org in organizations]


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
    initial_pass = body.initial_password or "OpenAgent@2026"
    res_u = await db.execute(select(User).where(User.email == body.email.lower()))
    invited_user = res_u.scalar_one_or_none()
    if not invited_user:
        invited_user = User(
            email=body.email.lower(),
            display_name=body.email.split("@", 1)[0],
            hashed_password=hash_password(initial_pass),
            is_active=True,
            lifecycle_status="active",
        )
        db.add(invited_user)
        await db.flush()
    else:
        invited_user.is_active = True
        invited_user.lifecycle_status = "active"
        if body.initial_password or not invited_user.hashed_password:
            invited_user.hashed_password = hash_password(initial_pass)
        await db.flush()

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
        provisioning_source="invite",
    )
    db.add(mem)
    await db.commit()
    await db.refresh(mem)

    await ZitadelProvisioningService().provision_user(
        email=invited_user.email,
        display_name=invited_user.display_name,
        initial_password=body.initial_password or "OpenAgent@2026",
    )

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

    if mem.role == Role.platform_admin:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "platform_admin members cannot be removed",
        )
    if user_id == current_user.id:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "You cannot remove your own membership",
        )
    if mem.role in (Role.org_admin, Role.admin):
        res_other_admins = await db.execute(
            select(Membership.user_id).where(
                Membership.org_id == id,
                Membership.user_id != user_id,
                Membership.role.in_([Role.org_admin, Role.admin]),
                Membership.lifecycle_status == "active",
            )
        )
        if res_other_admins.first() is None:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Cannot remove the last org_admin of the organization",
            )

    await db.delete(mem)

    # 1. Invalidate active sessions for this user within this organization
    await db.execute(
        update(ApplicationSession)
        .where(
            ApplicationSession.user_id == user_id,
            ApplicationSession.organization_id == id,
            ApplicationSession.revoked_at.is_(None),
        )
        .values(revoked_at=utc_now())
    )

    # 2. If user has no remaining active memberships, deactivate account
    res_other_mems = await db.execute(
        select(Membership).where(
            Membership.user_id == user_id,
            Membership.org_id != id,
            Membership.lifecycle_status == "active",
        )
    )
    if res_other_mems.first() is None:
        target_u = await db.get(User, user_id)
        if target_u:
            target_u.is_active = False
            target_u.lifecycle_status = "disabled"

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
    if get_settings().auth_provider == "zitadel":
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Product API keys require a provisioned service principal",
        )
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
