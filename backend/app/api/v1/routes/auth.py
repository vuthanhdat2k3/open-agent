from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.auth.jwt import (
    create_access_token,
    create_refresh_token,
    hash_refresh_token,
)
from app.core.auth.oauth import oauth
from app.core.auth.password import hash_password, verify_password
from app.core.observability.audit import log_action
from app.db.base import utc_now
from app.db.session import get_db
from app.dependencies import get_current_user
from app.models.membership import Membership
from app.models.oauth_account import OAuthAccount
from app.models.organization import Organization
from app.models.refresh_token import RefreshToken
from app.models.role import Role
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    MeResponse,
    RegisterRequest,
    TokenResponse,
    UserMembershipOut,
)
from app.services.quota_service import default_organization_quota

router = APIRouter(prefix="/api/auth", tags=["auth"])
settings = get_settings()


def _set_refresh_cookie(response: Response, raw_refresh_token: str) -> None:
    response.set_cookie(
        key="refresh_token",
        value=raw_refresh_token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=settings.jwt_refresh_ttl_days * 24 * 60 * 60,
    )


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterRequest, response: Response, db: AsyncSession = Depends(get_db)
):
    # Check if email exists
    res = await db.execute(select(User).where(User.email == body.email.lower()))
    if res.scalar_one_or_none():
        raise HTTPException(400, "Email already registered")

    # Create User
    display_name = body.display_name or body.email.split("@")[0]
    user = User(
        email=body.email.lower(),
        hashed_password=hash_password(body.password),
        display_name=display_name,
    )
    db.add(user)
    await db.flush()

    # Create Organization
    org_name = body.org_name or f"{display_name}'s Org"
    slug = f"{body.email.split('@')[0]}-{str(uuid.uuid4())[:8]}"
    org = Organization(name=org_name, slug=slug)
    db.add(org)
    await db.flush()
    db.add(default_organization_quota(org.id))

    # Create Membership
    membership = Membership(org_id=org.id, user_id=user.id, role=Role.owner)
    db.add(membership)

    # Issue Tokens
    access_token = create_access_token(user_id=user.id, org_id=org.id, role=Role.owner)
    raw_rt, rt_hash = create_refresh_token()
    now = utc_now()
    exp = now + timedelta(days=settings.jwt_refresh_ttl_days)

    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=rt_hash,
            expires_at=exp,
        )
    )
    await db.commit()

    _set_refresh_cookie(response, raw_rt)
    return TokenResponse(access_token=access_token)


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(select(User).where(User.email == body.email.lower()))
    user = res.scalar_one_or_none()

    if not user or not verify_password(body.password, user.hashed_password or ""):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")

    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "User account is inactive")

    # Get primary membership
    res_m = await db.execute(
        select(Membership).where(Membership.user_id == user.id).order_by(Membership.created_at)
    )
    membership = res_m.scalars().first()
    if not membership:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "User belongs to no organization")

    access_token = create_access_token(
        user_id=user.id, org_id=membership.org_id, role=membership.role
    )
    raw_rt, rt_hash = create_refresh_token()
    now = utc_now()
    exp = now + timedelta(days=settings.jwt_refresh_ttl_days)

    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=rt_hash,
            expires_at=exp,
        )
    )
    await db.commit()

    await log_action(
        db,
        org_id=membership.org_id,
        actor_user_id=user.id,
        action="login",
        resource_type="user",
        resource_id=user.id,
        ip=request.client.host if request.client else None,
    )

    _set_refresh_cookie(response, raw_rt)
    return TokenResponse(access_token=access_token)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token_route(
    request: Request, response: Response, db: AsyncSession = Depends(get_db)
):
    raw_rt = request.cookies.get("refresh_token")
    if not raw_rt:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing refresh token cookie")

    rt_hash = hash_refresh_token(raw_rt)
    res = await db.execute(select(RefreshToken).where(RefreshToken.token_hash == rt_hash))
    token_obj = res.scalar_one_or_none()

    now = utc_now()
    expires_at = token_obj.expires_at if token_obj else None
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    elif expires_at:
        expires_at = expires_at.astimezone(timezone.utc)

    if not token_obj or token_obj.revoked_at is not None or (expires_at and expires_at < now.replace(tzinfo=timezone.utc)):

        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or revoked refresh token")

    # Revoke old token (Rotation)
    token_obj.revoked_at = now

    # Check if user requested a specific active_org_id via cookie
    active_org_id = request.cookies.get("active_org_id")
    membership = None
    if active_org_id:
        res_m = await db.execute(
            select(Membership).where(
                Membership.user_id == token_obj.user_id,
                Membership.org_id == active_org_id,
            )
        )
        membership = res_m.scalar_one_or_none()

    if not membership:
        # Fallback to primary membership
        res_m = await db.execute(
            select(Membership).where(Membership.user_id == token_obj.user_id).order_by(Membership.created_at)
        )
        membership = res_m.scalars().first()

    org_id = membership.org_id if membership else "default-org-id"
    role = str(membership.role.value if hasattr(membership.role, "value") else membership.role) if membership else "developer"

    new_access_token = create_access_token(user_id=token_obj.user_id, org_id=org_id, role=role)
    new_raw_rt, new_rt_hash = create_refresh_token()
    exp = now + timedelta(days=settings.jwt_refresh_ttl_days)

    new_token_obj = RefreshToken(
        user_id=token_obj.user_id,
        token_hash=new_rt_hash,
        expires_at=exp,
    )
    db.add(new_token_obj)
    await db.flush()
    token_obj.replaced_by_id = new_token_obj.id

    await db.commit()
    _set_refresh_cookie(response, new_raw_rt)
    return TokenResponse(access_token=new_access_token)


@router.post("/logout")
async def logout(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    raw_rt = request.cookies.get("refresh_token")
    if raw_rt:
        rt_hash = hash_refresh_token(raw_rt)
        res = await db.execute(select(RefreshToken).where(RefreshToken.token_hash == rt_hash))
        token_obj = res.scalar_one_or_none()
        if token_obj and token_obj.revoked_at is None:
            token_obj.revoked_at = utc_now()
            await db.commit()

    response.delete_cookie("refresh_token")
    response.delete_cookie("active_org_id")
    return {"ok": True}


@router.get("/me", response_model=MeResponse)
async def me(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    res = await db.execute(
        select(Membership, Organization)
        .join(Organization, Membership.org_id == Organization.id)
        .where(Membership.user_id == current_user.id)
    )
    rows = res.all()
    memberships_out = [
        UserMembershipOut(
            org_id=org.id,
            org_name=org.name,
            org_slug=org.slug,
            role=mem.role,
        )
        for mem, org in rows
    ]

    return MeResponse(
        id=current_user.id,
        email=current_user.email,
        display_name=current_user.display_name,
        is_active=current_user.is_active,
        created_at=current_user.created_at,
        memberships=memberships_out,
    )


class SwitchOrgRequest(BaseModel):
    org_id: str


@router.post("/switch-org", response_model=TokenResponse)
async def switch_org(
    body: SwitchOrgRequest,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(
        select(Membership).where(
            Membership.user_id == current_user.id,
            Membership.org_id == body.org_id,
        )
    )
    membership = res.scalar_one_or_none()
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User does not belong to this organization",
        )

    role = str(membership.role.value if hasattr(membership.role, "value") else membership.role)
    access_token = create_access_token(
        user_id=current_user.id,
        org_id=membership.org_id,
        role=role,
    )
    response.set_cookie(
        key="active_org_id",
        value=membership.org_id,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=settings.jwt_refresh_ttl_days * 24 * 60 * 60,
    )
    return TokenResponse(access_token=access_token)



@router.get("/oauth/{provider}")
async def oauth_login(provider: str, request: Request):
    client = getattr(oauth, provider, None)
    if not client:
        raise HTTPException(400, f"OAuth provider '{provider}' not configured")
    redirect_uri = str(request.url_for("oauth_callback", provider=provider))
    return await client.authorize_redirect(request, redirect_uri)


@router.get("/oauth/{provider}/callback", name="oauth_callback")
async def oauth_callback(
    provider: str, request: Request, response: Response, db: AsyncSession = Depends(get_db)
):
    client = getattr(oauth, provider, None)
    if not client:
        raise HTTPException(400, f"OAuth provider '{provider}' not configured")

    token = await client.authorize_access_token(request)
    user_info = token.get("userinfo") or await client.userinfo(token)
    email = (user_info.get("email") or "").lower()
    provider_account_id = str(user_info.get("sub") or user_info.get("id"))

    if not email:
        raise HTTPException(400, "OAuth provider did not return email")

    # 1. Check existing OAuthAccount
    res_oauth = await db.execute(
        select(OAuthAccount).where(
            OAuthAccount.provider == provider,
            OAuthAccount.provider_account_id == provider_account_id,
        )
    )
    oauth_acc = res_oauth.scalar_one_or_none()

    if oauth_acc:
        res_u = await db.execute(select(User).where(User.id == oauth_acc.user_id))
        user = res_u.scalar_one()
    else:
        # Check existing User by email
        res_u = await db.execute(select(User).where(User.email == email))
        user = res_u.scalar_one_or_none()

        if not user:
            display_name = user_info.get("name") or user_info.get("login") or email.split("@")[0]
            user = User(email=email, display_name=display_name)
            db.add(user)
            await db.flush()

            # Create default Organization
            slug = f"{email.split('@')[0]}-{str(uuid.uuid4())[:8]}"
            org = Organization(name=f"{display_name}'s Org", slug=slug)
            db.add(org)
            await db.flush()
            db.add(default_organization_quota(org.id))

            membership = Membership(org_id=org.id, user_id=user.id, role=Role.owner)
            db.add(membership)

        # Create OAuthAccount link
        oauth_acc = OAuthAccount(
            user_id=user.id,
            provider=provider,
            provider_account_id=provider_account_id,
            access_token=token.get("access_token"),
            refresh_token=token.get("refresh_token"),
        )
        db.add(oauth_acc)

    res_m = await db.execute(
        select(Membership).where(Membership.user_id == user.id).order_by(Membership.created_at)
    )
    membership = res_m.scalars().first()

    access_token = create_access_token(
        user_id=user.id,
        org_id=membership.org_id if membership else "default-org-id",
        role=membership.role if membership else "owner",
    )
    raw_rt, rt_hash = create_refresh_token()
    now = utc_now()
    exp = now + timedelta(days=settings.jwt_refresh_ttl_days)

    db.add(RefreshToken(user_id=user.id, token_hash=rt_hash, expires_at=exp))
    await db.commit()

    _set_refresh_cookie(response, raw_rt)
    return TokenResponse(access_token=access_token)
