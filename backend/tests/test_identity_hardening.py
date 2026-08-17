from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config import Settings
from app.core.authz.policy import has_permission
from app.models.role import Role


def test_production_cannot_start_with_local_identity_authority() -> None:
    with pytest.raises(ValidationError, match="Production requires"):
        Settings(runtime="production", auth_provider="local")


def test_zitadel_settings_require_issuer_and_client() -> None:
    with pytest.raises(ValidationError, match="ZITADEL auth is enabled"):
        Settings(auth_provider="zitadel")


def test_operator_is_below_org_admin_and_above_user() -> None:
    assert has_permission(Role.org_admin, "billing:manage")
    assert has_permission(Role.operator, "agents:update")
    assert not has_permission(Role.operator, "billing:manage")
    assert not has_permission(Role.user, "agents:update")


def test_unknown_role_fails_closed() -> None:
    assert not has_permission("superadmin", "agents:read")  # type: ignore[arg-type]
