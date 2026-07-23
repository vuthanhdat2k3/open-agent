"""add oauth_account, refresh_token, and api_key tables

Revision ID: 0004_add_oauth_refresh_apikey
Revises: 0003_add_org_id_and_backfill
Create Date: 2026-07-23 00:00:02.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004_add_oauth_refresh_apikey"
down_revision: str | None = "0003_add_org_id_and_backfill"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # 1. oauth_accounts
    if not inspector.has_table("oauth_accounts"):
        op.create_table(
            "oauth_accounts",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("user_id", sa.String(length=36), nullable=False),
            sa.Column("provider", sa.String(length=64), nullable=False),
            sa.Column("provider_account_id", sa.String(length=255), nullable=False),
            sa.Column("access_token", sa.String(length=1024), nullable=True),
            sa.Column("refresh_token", sa.String(length=1024), nullable=True),
            sa.Column("expires_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("provider", "provider_account_id", name="uq_oauth_provider_account"),
        )
        op.create_index("ix_oauth_accounts_user_id", "oauth_accounts", ["user_id"])

    # 2. refresh_tokens
    if not inspector.has_table("refresh_tokens"):
        op.create_table(
            "refresh_tokens",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("user_id", sa.String(length=36), nullable=False),
            sa.Column("token_hash", sa.String(length=128), nullable=False),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
            sa.Column("revoked_at", sa.DateTime(), nullable=True),
            sa.Column("replaced_by_id", sa.String(length=36), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("token_hash"),
        )
        op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])
        op.create_index("ix_refresh_tokens_token_hash", "refresh_tokens", ["token_hash"])

    # 3. api_keys
    if not inspector.has_table("api_keys"):
        op.create_table(
            "api_keys",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("org_id", sa.String(length=36), nullable=False),
            sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
            sa.Column("name", sa.String(length=128), nullable=False),
            sa.Column("key_prefix", sa.String(length=16), nullable=False),
            sa.Column("key_hash", sa.String(length=128), nullable=False),
            sa.Column("expires_at", sa.DateTime(), nullable=True),
            sa.Column("revoked_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("key_hash"),
        )
        op.create_index("ix_api_keys_org_id", "api_keys", ["org_id"])
        op.create_index("ix_api_keys_key_prefix", "api_keys", ["key_prefix"])
        op.create_index("ix_api_keys_key_hash", "api_keys", ["key_hash"])


def downgrade() -> None:
    op.drop_table("api_keys")
    op.drop_table("refresh_tokens")
    op.drop_table("oauth_accounts")
