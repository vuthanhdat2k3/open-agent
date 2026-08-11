"""Add provider templates, encrypted keys, and model discovery lifecycle.

Revision ID: 0026_provider_templates
Revises: 0025_two_role_rbac

The API-key backfill is intentionally one-way: downgrade removes the encrypted
column but never reconstructs plaintext credentials that were zeroed by upgrade.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op
from app.core.credential_secrets import encrypt_string

revision = "0026_provider_templates"
down_revision = "0025_two_role_rbac"
branch_labels = None
depends_on = None


def _normalize(url: str) -> str:
    return (url or "").strip().rstrip("/").lower()


def upgrade() -> None:
    provider_columns = [
        sa.Column("normalized_base_url", sa.String(length=512), nullable=True),
        sa.Column("template_key", sa.String(length=32), nullable=True),
        sa.Column("api_key_encrypted", sa.Text(), nullable=True),
        sa.Column("api_key_last4", sa.String(length=8), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="ready"),
        sa.Column("discovery_status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("discovery_error", sa.Text(), nullable=True),
        sa.Column("models_discovered", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_discovery_attempt_at", sa.DateTime(), nullable=True),
        sa.Column("last_successful_discovery_at", sa.DateTime(), nullable=True),
    ]
    model_columns = [
        sa.Column("discovered", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("last_seen_at", sa.DateTime(), nullable=True),
        sa.Column("source", sa.String(length=16), nullable=False, server_default="manual"),
        sa.Column("catalog_source", sa.String(length=64), nullable=True),
        sa.Column("catalog_version", sa.String(length=16), nullable=True),
        sa.Column("last_discovered_at", sa.DateTime(), nullable=True),
        sa.Column("supports_tools", sa.Boolean(), nullable=True),
        sa.Column("supports_reasoning", sa.Boolean(), nullable=True),
        sa.Column("supports_vision", sa.Boolean(), nullable=True),
    ]
    for column in provider_columns:
        op.add_column("providers", column)
    for column in model_columns:
        op.add_column("models", column)

    bind = op.get_bind()
    providers = bind.execute(sa.text("SELECT id, base_url, api_key FROM providers")).mappings().all()
    for row in providers:
        raw_key = row["api_key"] or ""
        encrypted = encrypt_string(raw_key) if raw_key else None
        last4 = raw_key[-4:] if raw_key else None
        bind.execute(
            sa.text(
                "UPDATE providers SET normalized_base_url=:normalized, "
                "api_key_encrypted=:encrypted, api_key_last4=:last4, api_key='' WHERE id=:id"
            ),
            {
                "normalized": _normalize(row["base_url"]),
                "encrypted": encrypted,
                "last4": last4,
                "id": row["id"],
            },
        )

    bind.execute(
        sa.text(
            "UPDATE models SET discovered=FALSE, enabled=CASE WHEN active=TRUE THEN TRUE ELSE FALSE END, "
            "source='manual'"
        )
    )

    dialect = bind.dialect.name
    if dialect in {"sqlite", "postgresql"}:
        op.execute(
            "CREATE UNIQUE INDEX uq_providers_org_template_baseurl "
            "ON providers (org_id, template_key, normalized_base_url) "
            "WHERE template_key IS NOT NULL"
        )


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name
    if dialect in {"sqlite", "postgresql"}:
        op.execute("DROP INDEX IF EXISTS uq_providers_org_template_baseurl")

    for name in (
        "supports_vision",
        "supports_reasoning",
        "supports_tools",
        "last_discovered_at",
        "catalog_version",
        "catalog_source",
        "source",
        "last_seen_at",
        "enabled",
        "discovered",
    ):
        op.drop_column("models", name)
    for name in (
        "last_successful_discovery_at",
        "last_discovery_attempt_at",
        "models_discovered",
        "discovery_error",
        "discovery_status",
        "status",
        "api_key_last4",
        "api_key_encrypted",
        "template_key",
        "normalized_base_url",
    ):
        op.drop_column("providers", name)
