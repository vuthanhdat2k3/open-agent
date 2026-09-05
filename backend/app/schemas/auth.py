from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    display_name: str | None = None
    org_name: str | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserMembershipOut(BaseModel):
    org_id: str
    org_name: str
    org_slug: str
    role: str
    # A user can hold more than one role in the same org (e.g. a
    # self-registered founder gets both org_admin and operator) - `role` is
    # the highest-priority one for display, `roles` is the full set.
    roles: list[str] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class MeResponse(BaseModel):
    id: str
    email: str
    display_name: str
    is_active: bool
    must_change_password: bool = False
    created_at: datetime
    memberships: list[UserMembershipOut]
    permissions_by_org: dict[str, list[str]] = Field(default_factory=dict)
    active_org_id: str | None = None

    model_config = ConfigDict(from_attributes=True)


class InviteMemberRequest(BaseModel):
    email: EmailStr
    role: str = "user"
    initial_password: str | None = None


class UpdateMemberRoleRequest(BaseModel):
    role: str


class ApiKeyCreateRequest(BaseModel):
    name: str
    expires_days: int | None = None


class ApiKeyOut(BaseModel):
    id: str
    org_id: str
    name: str
    key_prefix: str
    expires_at: datetime | None = None
    revoked_at: datetime | None = None
    service_principal_id: str | None = None
    scopes: list[str] = Field(default_factory=list)
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ApiKeyCreateResponse(BaseModel):
    api_key: ApiKeyOut
    secret_key: str
