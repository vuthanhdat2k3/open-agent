from __future__ import annotations

import base64
import hashlib
import logging
import secrets
import uuid
from datetime import timedelta, timezone
from urllib.parse import urlsplit, urlunsplit

import httpx
import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.auth.application_session import (
    clear_application_session,
    create_application_session,
    resolve_application_session,
)
from app.core.auth.jwt import (
    create_access_token,
    create_refresh_token,
    hash_refresh_token,
)
from app.core.auth.oauth import oauth
from app.core.auth.password import hash_password, verify_password
from app.core.observability.audit import log_action
from app.core.authz.policy import PERMISSIONS
from app.db.base import utc_now
from app.db.session import get_db
from app.dependencies import get_current_user
from app.models.membership import Membership
from app.models.oauth_account import OAuthAccount
from app.models.oidc_login_transaction import OidcLoginTransaction
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
logger = logging.getLogger(__name__)


def _public_role(role: Role) -> str:
    if get_settings().auth_provider == "local" and role == Role.org_admin:
        return "admin"
    return role.value


def _require_local_auth() -> None:
    if get_settings().auth_provider == "zitadel":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Legacy authentication surface is disabled")


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


async def _oidc_discovery() -> dict[str, str]:
    issuer = get_settings().zitadel_issuer_url.rstrip("/")
    if not issuer:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "ZITADEL is not configured")
    discovery_base = (get_settings().zitadel_internal_url or issuer).rstrip("/")
    public_host = issuer.removeprefix("http://").removeprefix("https://").split("/", 1)[0]
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            f"{discovery_base}/.well-known/openid-configuration",
            headers={"Host": public_host},
        )
    response.raise_for_status()
    return response.json()


def _internal_oidc_url(external_url: str, internal_base: str) -> str:
    """Route OIDC back-channel calls through Docker while preserving the public host."""
    external = urlsplit(external_url)
    internal = urlsplit(internal_base.rstrip("/"))
    return urlunsplit((internal.scheme, internal.netloc, external.path, external.query, external.fragment))


@router.get("/login")
async def oidc_login(
    request: Request,
    organization: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    if get_settings().auth_provider != "zitadel":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ZITADEL authentication is not enabled")
    discovery = await _oidc_discovery()
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    organization_id = None
    if organization:
        result = await db.execute(select(Organization).where(Organization.slug == organization))
        org = result.scalar_one_or_none()
        if org is None or org.lifecycle_status != "active":
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Organization not found")
        organization_id = org.id
    transaction = OidcLoginTransaction(
        state_hash=_digest(state),
        nonce_hash=_digest(nonce),
        code_verifier=verifier,
        organization_id=organization_id,
        redirect_uri=get_settings().zitadel_redirect_uri,
        expires_at=utc_now() + timedelta(minutes=10),
    )
    db.add(transaction)
    await db.commit()
    params = {
        "client_id": get_settings().zitadel_client_id,
        "response_type": "code",
        "redirect_uri": get_settings().zitadel_redirect_uri,
        "scope": "openid profile email",
        "state": state,
        "nonce": nonce,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    if organization:
        params["organization"] = organization
    query = httpx.QueryParams(params)
    return RedirectResponse(f"{discovery['authorization_endpoint']}?{query}", status_code=307)


@router.get("/callback")
async def oidc_callback(
    request: Request,
    response: Response,
    code: str,
    state: str,
    db: AsyncSession = Depends(get_db),
):
    if get_settings().auth_provider != "zitadel":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ZITADEL authentication is not enabled")
    transaction_result = await db.execute(
        select(OidcLoginTransaction).where(OidcLoginTransaction.state_hash == _digest(state))
    )
    transaction = transaction_result.scalar_one_or_none()
    now = utc_now()
    if transaction is None or transaction.consumed_at is not None or transaction.expires_at < now:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired login transaction")
    transaction.consumed_at = now
    discovery = await _oidc_discovery()
    internal_base = get_settings().zitadel_internal_url or get_settings().zitadel_issuer_url
    public_host = get_settings().zitadel_issuer_url.removeprefix("http://").removeprefix("https://").split("/", 1)[0]
    async with httpx.AsyncClient(timeout=15.0) as client:
        token_response = await client.post(
            _internal_oidc_url(discovery["token_endpoint"], internal_base),
            headers={"Host": public_host},
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": transaction.redirect_uri,
                "client_id": get_settings().zitadel_client_id,
                "client_secret": get_settings().zitadel_client_secret,
                "code_verifier": transaction.code_verifier,
            },
        )
    if token_response.status_code >= 400:
        await db.rollback()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authorization code exchange failed")
    token = token_response.json()
    id_token = token.get("id_token")
    if not id_token:
        await db.rollback()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "ZITADEL did not return an ID token")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            jwks_response = await client.get(
                _internal_oidc_url(discovery["jwks_uri"], internal_base),
                headers={"Host": public_host},
            )
        jwks_response.raise_for_status()
        jwks = jwt.PyJWKSet.from_json(jwks_response.text)
        key_id = jwt.get_unverified_header(id_token).get("kid")
        signing_key = next((key.key for key in jwks.keys if key.key_id == key_id), None)
        if signing_key is None:
            await db.rollback()
            logger.error("OIDC ID token signing key was not found", extra={"kid": key_id})
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "ZITADEL signing key not found")
        claims = jwt.decode(
            id_token,
            signing_key,
            algorithms=["RS256", "RS384", "RS512"],
            audience=get_settings().zitadel_client_id,
            issuer=get_settings().zitadel_issuer_url.rstrip("/"),
        )
    except jwt.PyJWTError as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid ZITADEL ID token") from exc
    if _digest(str(claims.get("nonce", ""))) != transaction.nonce_hash:
        await db.rollback()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid OIDC nonce")
    zitadel_user_id = str(claims.get("sub", ""))
    claim_email = str(claims.get("email", "")).strip().lower()
    if not claim_email and token.get("access_token"):
        async with httpx.AsyncClient(timeout=10.0) as client:
            userinfo_response = await client.get(
                _internal_oidc_url(discovery["userinfo_endpoint"], internal_base),
                headers={"Host": public_host, "Authorization": f"Bearer {token['access_token']}"},
            )
        if userinfo_response.is_success:
            claim_email = str(userinfo_response.json().get("email", "")).strip().lower()
    result = await db.execute(select(User).where(User.zitadel_user_id == zitadel_user_id))
    user = result.scalar_one_or_none()
    if user is None and claim_email:
        # Existing disposable/local accounts may be linked only after a
        # verified identity has authenticated at ZITADEL. No account is
        # created for ordinary users (the callback remains fail-closed).
        result = await db.execute(select(User).where(User.email == claim_email))
        user = result.scalar_one_or_none()
        if user is not None and user.zitadel_user_id in {None, zitadel_user_id}:
            user.zitadel_user_id = zitadel_user_id
    if user is None and claim_email in get_settings().platform_admin_email_set:
        user = User(
            email=claim_email,
            zitadel_user_id=zitadel_user_id,
            display_name=str(claims.get("name") or claim_email.split("@", 1)[0])[:128],
        )
        db.add(user)
        await db.flush()
        system_org_result = await db.execute(select(Organization).where(Organization.slug == "platform"))
        system_org = system_org_result.scalar_one_or_none()
        if system_org is None:
            system_org = Organization(name="OpenAgent Platform", slug="platform", provisioning_mode="managed")
            db.add(system_org)
            await db.flush()
            db.add(default_organization_quota(system_org.id))
        db.add(Membership(org_id=system_org.id, user_id=user.id, role=Role.platform_admin))
    if user is None or not user.is_active or user.lifecycle_status != "active":
        await db.rollback()
        raise HTTPException(status.HTTP_403_FORBIDDEN, "ACCOUNT_NOT_PROVISIONED")
    org_claim = claims.get(get_settings().zitadel_required_org_claim) or claims.get("org_id")
    if isinstance(org_claim, list):
        org_claim = org_claim[0] if len(org_claim) == 1 else None
    if transaction.organization_id:
        org_result = await db.execute(select(Organization).where(Organization.id == transaction.organization_id))
        expected_org = org_result.scalar_one_or_none()
        if expected_org is None or (org_claim and org_claim not in {expected_org.id, expected_org.zitadel_org_id}):
            await db.rollback()
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Organization context mismatch")
        organization_id = expected_org.id
    else:
        platform_membership_result = await db.execute(
            select(Membership)
            .join(Organization, Organization.id == Membership.org_id)
            .where(
                Membership.user_id == user.id,
                Membership.role == Role.platform_admin,
                Membership.lifecycle_status == "active",
                Organization.slug == "platform",
            )
        )
        platform_membership = platform_membership_result.scalar_one_or_none()
        if platform_membership is not None:
            organization_id = transaction.organization_id or platform_membership.org_id
        else:
            if org_claim:
                org_result = await db.execute(select(Organization).where(Organization.zitadel_org_id == org_claim))
                org = org_result.scalar_one_or_none()
                if org is None:
                    await db.rollback()
                    raise HTTPException(status.HTTP_403_FORBIDDEN, "ACCOUNT_NOT_PROVISIONED")
                organization_id = org.id
            else:
                memberships_result = await db.execute(
                    select(Membership).where(
                        Membership.user_id == user.id,
                        Membership.lifecycle_status == "active",
                    )
                )
                memberships = memberships_result.scalars().all()
                if len(memberships) != 1:
                    await db.rollback()
                    raise HTTPException(status.HTTP_403_FORBIDDEN, "ORGANIZATION_CONTEXT_REQUIRED")
                organization_id = memberships[0].org_id
    membership_result = await db.execute(
        select(Membership).where(
            Membership.user_id == user.id,
            Membership.org_id == organization_id,
            Membership.lifecycle_status == "active",
        )
    )
    membership = membership_result.scalar_one_or_none()
    if membership is None:
        await db.rollback()
        raise HTTPException(status.HTTP_403_FORBIDDEN, "ACCOUNT_NOT_PROVISIONED")
    if claims.get("email") and not user.email:
        user.email = str(claims["email"]).lower()
    if claims.get("name"):
        user.display_name = str(claims["name"])[:128]
    redirect = RedirectResponse(get_settings().zitadel_post_logout_redirect_uri, status_code=303)
    await create_application_session(
        db,
        user=user,
        membership=membership,
        request=request,
        response=redirect,
        zitadel_session_id=claims.get("sid"),
    )
    await db.commit()
    return redirect


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
    _require_local_auth()
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
    membership = Membership(org_id=org.id, user_id=user.id, role=Role.org_admin)
    db.add(membership)

    # Issue Tokens
    access_token = create_access_token(user_id=user.id, org_id=org.id, role=Role.org_admin)
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
    _require_local_auth()
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
    _require_local_auth()
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

    if membership is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "User belongs to no organization")
    org_id = membership.org_id
    role = str(membership.role.value if hasattr(membership.role, "value") else membership.role)

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
    if get_settings().auth_provider == "zitadel":
        raw_session = request.cookies.get(get_settings().application_session_cookie_name)
        if raw_session:
            try:
                _, _, application_session = await resolve_application_session(
                    db, raw_token=raw_session, request=request
                )
                application_session.revoked_at = utc_now()
                application_session.revocation_reason = "logout"
                await db.commit()
            except HTTPException:
                # Logout remains idempotent, while an invalid CSRF token does
                # not revoke a valid session.
                await db.rollback()
        clear_application_session(response)
        return {"ok": True}
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
async def me(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
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
            role=_public_role(mem.role),
        )
        for mem, org in rows
    ]
    permissions_by_org = {
        org.id: sorted(PERMISSIONS.get(mem.role, set()))
        for mem, org in rows
    }

    return MeResponse(
        id=current_user.id,
        email=current_user.email,
        display_name=current_user.display_name,
        is_active=current_user.is_active,
        created_at=current_user.created_at,
        memberships=memberships_out,
        permissions_by_org=permissions_by_org,
        active_org_id=getattr(request.state, "org_id", None),
    )


class UpdateProfileRequest(BaseModel):
    display_name: str | None = None
    old_password: str | None = None
    new_password: str | None = None


@router.patch("/me", response_model=MeResponse)
async def update_me(
    body: UpdateProfileRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_local_auth()
    if body.display_name is not None:
        current_user.display_name = body.display_name.strip()

    if body.new_password:
        if not body.old_password:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Old password is required to set a new password")
        if not verify_password(body.old_password, current_user.hashed_password or ""):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Incorrect old password")
        current_user.hashed_password = hash_password(body.new_password)

    await db.commit()
    await db.refresh(current_user)
    return await me(request=request, current_user=current_user, db=db)


class SwitchOrgRequest(BaseModel):
    org_id: str


@router.post("/switch-org")
async def switch_org(
    body: SwitchOrgRequest,
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    platform_membership = await db.scalar(
        select(Membership).where(
            Membership.user_id == current_user.id,
            Membership.role == Role.platform_admin,
            Membership.lifecycle_status == "active",
        )
    )
    res = await db.execute(
        select(Membership).where(
            Membership.user_id == current_user.id,
            Membership.org_id == body.org_id,
        )
    )
    membership = res.scalar_one_or_none()
    if platform_membership and not membership:
        organization = await db.scalar(
            select(Organization).where(
                Organization.id == body.org_id,
                Organization.lifecycle_status == "active",
            )
        )
        if organization:
            membership = Membership(
                org_id=organization.id,
                user_id=current_user.id,
                role=Role.platform_admin,
                provisioning_source="platform",
            )
            db.add(membership)
            await db.flush()
    elif platform_membership and membership and membership.role != Role.platform_admin:
        membership.role = Role.platform_admin
        await db.flush()
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User does not belong to this organization",
        )

    if get_settings().auth_provider == "zitadel":
        raw_session = request.cookies.get(get_settings().application_session_cookie_name)
        if not raw_session:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Application session required")
        _, _, old_session = await resolve_application_session(db, raw_token=raw_session, request=request)
        old_session.revoked_at = utc_now()
        old_session.revocation_reason = "organization_switched"
        await create_application_session(
            db,
            user=current_user,
            membership=membership,
            request=request,
            response=response,
        )
        await db.commit()
        return {"ok": True}

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
    _require_local_auth()
    client = getattr(oauth, provider, None)
    if not client:
        raise HTTPException(400, f"OAuth provider '{provider}' not configured")
    redirect_uri = str(request.url_for("oauth_callback", provider=provider))
    return await client.authorize_redirect(request, redirect_uri)


@router.get("/oauth/{provider}/callback", name="oauth_callback")
async def oauth_callback(
    provider: str, request: Request, response: Response, db: AsyncSession = Depends(get_db)
):
    _require_local_auth()
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

            membership = Membership(org_id=org.id, user_id=user.id, role=Role.admin)
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
    if membership is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "User belongs to no organization")

    access_token = create_access_token(
        user_id=user.id,
        org_id=membership.org_id,
        role=membership.role,
    )
    raw_rt, rt_hash = create_refresh_token()
    now = utc_now()
    exp = now + timedelta(days=settings.jwt_refresh_ttl_days)

    db.add(RefreshToken(user_id=user.id, token_hash=rt_hash, expires_at=exp))
    await db.commit()

    _set_refresh_cookie(response, raw_rt)
    return TokenResponse(access_token=access_token)
