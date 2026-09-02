from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.agents.sync import sync_system_agents_for_org
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
    UpdateMemberRoleRequest,
)
from app.services.quota_service import default_organization_quota
from app.services.rag_mcp_bootstrap import ensure_rag_mcp_server
from app.services.zitadel_service import ZitadelProvisioningService

router = APIRouter(prefix="/api/orgs", tags=["orgs"])


class OrgCreateRequest(BaseModel):
    name: str
    admin_email: str | None = None
    initial_password: str | None = None


class OrgRenameRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)


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


async def _is_platform_admin(db: AsyncSession, user_id: str) -> bool:
    result = await db.execute(
        select(Membership).join(Organization, Membership.org_id == Organization.id).where(
            Membership.user_id == user_id,
            Membership.role == Role.platform_admin,
            Membership.lifecycle_status == "active",
        )
    )
    return result.scalars().first() is not None


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
    await ensure_rag_mcp_server(db, org.id)

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
                must_change_password=True,
            )
            db.add(target_user)
            await db.flush()
        else:
            if body.initial_password or not target_user.hashed_password:
                target_user.hashed_password = hash_password(initial_pass)
                target_user.must_change_password = True
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

    await sync_system_agents_for_org(db, org.id)
    await db.commit()
    await db.refresh(org)
    return OrgOut(id=org.id, name=org.name, slug=org.slug, created_at=org.created_at)


@router.patch("/{id}", response_model=OrgOut)
async def rename_org(
    id: str,
    body: OrgRenameRequest,
    current_user: User = Depends(require_platform_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Organization).where(Organization.id == id))
    org = result.scalar_one_or_none()
    if org is None or org.lifecycle_status == "deleted":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Organization not found")
    if org.slug == "platform":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The platform organization cannot be renamed")

    name = body.name.strip()
    if not name:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Organization name cannot be empty")
    old_name = org.name
    org.name = name
    await log_action(
        db,
        org_id=id,
        actor_user_id=current_user.id,
        action="organization.renamed",
        resource_type="organization",
        resource_id=id,
        metadata={"old_name": old_name, "new_name": name},
        commit=False,
    )
    await db.commit()
    await db.refresh(org)
    return OrgOut(id=org.id, name=org.name, slug=org.slug, created_at=org.created_at)


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_org(
    id: str,
    current_user: User = Depends(require_platform_admin),
    db: AsyncSession = Depends(get_db),
):
    """Revoke a tenant organization without destroying its historical data."""
    result = await db.execute(select(Organization).where(Organization.id == id))
    org = result.scalar_one_or_none()
    if org is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Organization not found")
    if org.slug == "platform":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The platform organization cannot be deleted")
    if org.lifecycle_status == "deleted":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Organization not found")

    await db.execute(
        update(Membership)
        .where(Membership.org_id == id, Membership.lifecycle_status == "active")
        .values(lifecycle_status="revoked")
    )
    await db.execute(
        update(ApplicationSession)
        .where(ApplicationSession.organization_id == id, ApplicationSession.revoked_at.is_(None))
        .values(revoked_at=utc_now(), revocation_reason="organization_deleted")
    )
    org.lifecycle_status = "deleted"
    await log_action(
        db,
        org_id=id,
        actor_user_id=current_user.id,
        action="organization.deleted",
        resource_type="organization",
        resource_id=id,
        commit=False,
    )
    await db.commit()
    return None


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
        result = await db.execute(
            select(Organization)
            .where(Organization.lifecycle_status == "active")
            .order_by(Organization.created_at.desc())
        )
        organizations = result.scalars().all()
    else:
        org_ids = [mem.org_id for mem in memberships]
        result = await db.execute(
            select(Organization)
            .where(Organization.id.in_(org_ids), Organization.lifecycle_status == "active")
            .order_by(Organization.created_at.desc())
        )
        organizations = result.scalars().all()
    return [OrgOut(id=org.id, name=org.name, slug=org.slug, created_at=org.created_at) for org in organizations]


@router.get("/{id}/members", response_model=list[OrgMemberOut], dependencies=[Depends(require_permission("orgs:manage"))])
async def list_org_members(
    id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _ensure_user_belongs_to_org(db, current_user.id, id)
    res = await db.execute(
        select(Membership, User)
        .join(User, Membership.user_id == User.id)
        .where(
            Membership.org_id == id,
            Membership.role != Role.platform_admin,
        )
    )
    rows = res.all()
    return [
        OrgMemberOut(
            user_id=u.id,
            email=u.email,
            display_name=u.display_name,
            role=mem.role.value,
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
            must_change_password=True,
        )
        db.add(invited_user)
        await db.flush()
    else:
        invited_user.is_active = True
        invited_user.lifecycle_status = "active"
        if body.initial_password or not invited_user.hashed_password:
            invited_user.hashed_password = hash_password(initial_pass)
            # An admin just (re)chose this password: force a self-chosen one.
            invited_user.must_change_password = True
        await db.flush()

    res_mem = await db.execute(
        select(Membership).where(Membership.org_id == id, Membership.user_id == invited_user.id)
    )
    if res_mem.scalar_one_or_none():
        raise HTTPException(400, "User is already a member of this organization")

    role_val = {
        "org_admin": Role.org_admin,
        "operator": Role.operator,
        "user": Role.user,
    }.get(body.role)
    if role_val is None:
        raise HTTPException(400, f"Invalid role: {body.role}")
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
        role=mem.role.value,
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
    if mem.role == Role.org_admin:
        res_other_admins = await db.execute(
            select(Membership.user_id).where(
                Membership.org_id == id,
                Membership.user_id != user_id,
                Membership.role == Role.org_admin,
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


@router.patch(
    "/{id}/members/{user_id}",
    response_model=OrgMemberOut,
    dependencies=[Depends(require_permission("orgs:manage"))],
)
async def update_org_member_role(
    id: str,
    user_id: str,
    body: UpdateMemberRoleRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Change an existing member's role (org_admin+, ``orgs:manage``)."""
    new_role = {
        "org_admin": Role.org_admin,
        "operator": Role.operator,
        "user": Role.user,
    }.get(body.role)
    if new_role is None:
        raise HTTPException(400, f"Invalid role: {body.role}")

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
            "The platform_admin role cannot be changed here",
        )
    if user_id == current_user.id:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "You cannot change your own role",
        )
    if mem.role == Role.org_admin and new_role != Role.org_admin:
        res_other_admins = await db.execute(
            select(Membership.user_id).where(
                Membership.org_id == id,
                Membership.user_id != user_id,
                Membership.role == Role.org_admin,
                Membership.lifecycle_status == "active",
            )
        )
        if res_other_admins.first() is None:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Cannot demote the last org_admin of the organization",
            )

    if mem.role != new_role:
        old_role = mem.role.value
        mem.role = new_role
        await db.commit()
        await db.refresh(mem)
        await log_action(
            db,
            org_id=id,
            actor_user_id=current_user.id,
            action="membership.role_changed",
            resource_type="membership",
            resource_id=user_id,
            metadata={"old_role": old_role, "new_role": new_role.value},
        )

    member_user = await db.get(User, mem.user_id)
    return OrgMemberOut(
        user_id=mem.user_id,
        email=member_user.email if member_user else "",
        display_name=member_user.display_name if member_user else "",
        role=mem.role.value,
        created_at=mem.created_at,
    )


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
