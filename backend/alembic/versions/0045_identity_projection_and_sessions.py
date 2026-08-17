"""Add ZITADEL identity projection fields and opaque application sessions."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# PostgreSQL's default alembic_version.version_num is VARCHAR(32).
# Keep this revision identifier within that limit so startup migrations work
# against existing databases as well as fresh installations.
revision: str = "0045_identity_sessions"
down_revision: str | None = "0044_durable_file_ingestion"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("organizations") as batch:
        batch.add_column(sa.Column("zitadel_org_id", sa.String(length=128), nullable=True))
        batch.add_column(sa.Column("lifecycle_status", sa.String(length=24), server_default="active", nullable=False))
        batch.add_column(sa.Column("provisioning_mode", sa.String(length=24), server_default="managed", nullable=False))
    op.create_index("uq_organizations_zitadel_org_id", "organizations", ["zitadel_org_id"], unique=True)

    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("zitadel_user_id", sa.String(length=128), nullable=True))
        batch.add_column(sa.Column("lifecycle_status", sa.String(length=24), server_default="active", nullable=False))
    op.create_index("uq_users_zitadel_user_id", "users", ["zitadel_user_id"], unique=True)

    with op.batch_alter_table("memberships") as batch:
        batch.add_column(sa.Column("lifecycle_status", sa.String(length=24), server_default="active", nullable=False))
        batch.add_column(sa.Column("provisioning_source", sa.String(length=24), server_default="platform", nullable=False))
        batch.add_column(sa.Column("zitadel_role_assignment_id", sa.String(length=128), nullable=True))

    op.create_table(
        "application_sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("session_token_hash", sa.String(length=128), nullable=False),
        sa.Column("csrf_token_hash", sa.String(length=128), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("membership_id", sa.String(length=36), nullable=False),
        sa.Column("zitadel_session_id", sa.String(length=128), nullable=True),
        sa.Column("auth_time", sa.DateTime(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False),
        sa.Column("idle_expires_at", sa.DateTime(), nullable=False),
        sa.Column("absolute_expires_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("revocation_reason", sa.String(length=128), nullable=True),
        sa.Column("created_ip_hash", sa.String(length=128), nullable=True),
        sa.Column("created_user_agent_hash", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["membership_id"], ["memberships.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_token_hash"),
    )
    op.create_index("ix_application_sessions_session_token_hash", "application_sessions", ["session_token_hash"])
    op.create_index("ix_application_sessions_user_id", "application_sessions", ["user_id"])
    op.create_index("ix_application_sessions_organization_id", "application_sessions", ["organization_id"])
    op.create_index("ix_application_sessions_membership_id", "application_sessions", ["membership_id"])

    op.create_table(
        "oidc_login_transactions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("state_hash", sa.String(length=128), nullable=False),
        sa.Column("nonce_hash", sa.String(length=128), nullable=False),
        sa.Column("code_verifier", sa.String(length=128), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=True),
        sa.Column("redirect_uri", sa.String(length=512), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("consumed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("state_hash"),
    )
    op.create_index("ix_oidc_login_transactions_state_hash", "oidc_login_transactions", ["state_hash"])
    op.create_index("ix_oidc_login_transactions_organization_id", "oidc_login_transactions", ["organization_id"])


def downgrade() -> None:
    op.drop_index("ix_oidc_login_transactions_organization_id", table_name="oidc_login_transactions")
    op.drop_index("ix_oidc_login_transactions_state_hash", table_name="oidc_login_transactions")
    op.drop_table("oidc_login_transactions")
    op.drop_index("ix_application_sessions_membership_id", table_name="application_sessions")
    op.drop_index("ix_application_sessions_organization_id", table_name="application_sessions")
    op.drop_index("ix_application_sessions_user_id", table_name="application_sessions")
    op.drop_index("ix_application_sessions_session_token_hash", table_name="application_sessions")
    op.drop_table("application_sessions")
    with op.batch_alter_table("memberships") as batch:
        batch.drop_column("zitadel_role_assignment_id")
        batch.drop_column("provisioning_source")
        batch.drop_column("lifecycle_status")
    op.drop_index("uq_users_zitadel_user_id", table_name="users")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("lifecycle_status")
        batch.drop_column("zitadel_user_id")
    op.drop_index("uq_organizations_zitadel_org_id", table_name="organizations")
    with op.batch_alter_table("organizations") as batch:
        batch.drop_column("provisioning_mode")
        batch.drop_column("lifecycle_status")
        batch.drop_column("zitadel_org_id")
