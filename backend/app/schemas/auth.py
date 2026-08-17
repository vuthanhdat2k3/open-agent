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

    model_config = ConfigDict(from_attributes=True)


class MeResponse(BaseModel):
    id: str
    email: str
    display_name: str
    is_active: bool
    created_at: datetime
    memberships: list[UserMembershipOut]

    model_config = ConfigDict(from_attributes=True)


class InviteMemberRequest(BaseModel):
    email: EmailStr
    role: str = "developer"


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
