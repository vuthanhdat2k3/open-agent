from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config import Settings
from app.core.authz.policy import has_permission
from app.models.role import Role

# The repo's parent-directory `.env` (the main worktree's real, populated
# config) is picked up by `app.main`'s bare `load_dotenv()` call before any
# test body runs, regardless of which directory pytest is invoked from.
# `pydantic-settings` treats anything already in `os.environ` as an override
# of the field default, so a test that asserts *default* behavior (no
# explicit kwarg) is not hermetic unless it clears those specific vars
# first. Tests below that pass every relevant field explicitly (see
# `_PROD_OK_KWARGS`) are unaffected, because an explicit kwarg always wins
# over `os.environ` in pydantic-settings' source-precedence order.
_ENV_LEAK_VARS = (
    "OPENAGENT_ZITADEL_ISSUER_URL",
    "OPENAGENT_ZITADEL_INTERNAL_URL",
    "OPENAGENT_ZITADEL_PROJECT_ID",
    "OPENAGENT_ZITADEL_CLIENT_ID",
    "OPENAGENT_ZITADEL_CLIENT_SECRET",
    "OPENAGENT_ZITADEL_ADMIN_PAT",
    "OPENAGENT_ZITADEL_REDIRECT_URI",
    "OPENAGENT_ZITADEL_POST_LOGOUT_REDIRECT_URI",
    "OPENAGENT_AUTH_PROVIDER",
    "OPENAGENT_JWT_SECRET_KEY",
    "OPENAGENT_COOKIE_SECURE",
    "OPENAGENT_S3_ACCESS_KEY",
    "OPENAGENT_S3_SECRET_KEY",
)


@pytest.fixture
def clean_settings_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strip the leaked parent-.env overrides so ``Settings()`` defaults
    reflect the field declarations in app/config.py, not this machine's
    ambient environment."""
    for name in _ENV_LEAK_VARS:
        monkeypatch.delenv(name, raising=False)


def test_production_cannot_start_with_local_identity_authority() -> None:
    with pytest.raises(ValidationError, match="Production requires"):
        Settings(runtime="production", auth_provider="local")


def test_zitadel_settings_require_issuer_and_client(clean_settings_env: None) -> None:
    with pytest.raises(ValidationError, match="ZITADEL auth is enabled"):
        Settings(auth_provider="zitadel")


_PROD_OK_KWARGS = dict(
    runtime="production",
    auth_provider="zitadel",
    zitadel_issuer_url="https://auth.example.com",
    zitadel_client_id="client-id",
    zitadel_redirect_uri="https://app.example.com/api/auth/callback",
    jwt_secret_key="a" * 32,
    cookie_secure=True,
    s3_access_key="prod-access-key",
    s3_secret_key="prod-secret-key",
)


def test_production_rejects_default_jwt_secret() -> None:
    with pytest.raises(ValidationError, match="OPENAGENT_JWT_SECRET_KEY"):
        Settings(**{**_PROD_OK_KWARGS, "jwt_secret_key": "dev-secret-key-change-in-production"})


def test_production_rejects_short_jwt_secret() -> None:
    with pytest.raises(ValidationError, match="OPENAGENT_JWT_SECRET_KEY"):
        Settings(**{**_PROD_OK_KWARGS, "jwt_secret_key": "short"})


def test_production_requires_secure_cookies() -> None:
    with pytest.raises(ValidationError, match="OPENAGENT_COOKIE_SECURE"):
        Settings(**{**_PROD_OK_KWARGS, "cookie_secure": False})


def test_production_rejects_default_minio_access_key() -> None:
    with pytest.raises(ValidationError, match="OPENAGENT_S3_ACCESS_KEY"):
        Settings(**{**_PROD_OK_KWARGS, "s3_access_key": "minioadmin"})


def test_production_rejects_default_minio_secret_key() -> None:
    with pytest.raises(ValidationError, match="OPENAGENT_S3_ACCESS_KEY"):
        Settings(**{**_PROD_OK_KWARGS, "s3_secret_key": "minioadmin"})


def test_production_reports_every_insecure_default_at_once() -> None:
    """A deployment fixing secrets one at a time should see every remaining
    problem on each attempt, not just the first one alphabetically."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            **{
                **_PROD_OK_KWARGS,
                "jwt_secret_key": "dev-secret-key-change-in-production",
                "cookie_secure": False,
                "s3_access_key": "minioadmin",
            }
        )
    message = str(exc_info.value)
    assert "OPENAGENT_JWT_SECRET_KEY" in message
    assert "OPENAGENT_COOKIE_SECURE" in message
    assert "OPENAGENT_S3_ACCESS_KEY" in message


def test_production_accepts_properly_overridden_secrets() -> None:
    settings = Settings(**_PROD_OK_KWARGS)
    assert settings.runtime == "production"
    assert settings.cookie_secure is True


def test_local_runtime_ignores_insecure_defaults(clean_settings_env: None) -> None:
    """The validator is production-only: local/dev checkouts must keep
    working with zero configuration."""
    settings = Settings(runtime="local")
    assert settings.jwt_secret_key == "dev-secret-key-change-in-production"
    assert settings.cookie_secure is False
    assert settings.s3_access_key == "minioadmin"


def test_operator_and_org_admin_are_non_overlapping() -> None:
    # org_admin manages the org, not the AI stack; operator is the reverse -
    # the two roles no longer form a hierarchy (see policy.py header comment).
    assert has_permission(Role.org_admin, "orgs:manage")
    assert not has_permission(Role.org_admin, "agents:update")
    assert has_permission(Role.operator, "agents:update")
    assert not has_permission(Role.operator, "orgs:manage")
    assert not has_permission(Role.user, "agents:update")


def test_unknown_role_fails_closed() -> None:
    assert not has_permission("superadmin", "agents:read")  # type: ignore[arg-type]
