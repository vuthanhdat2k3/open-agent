"""add a2a and agent identity tables and columns

Revision ID: 0020_a2a_and_agent_identity
Revises: 0019_auto_rollback
Create Date: 2026-08-03
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0020_a2a_and_agent_identity"
down_revision: str | None = "0019_auto_rollback"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Create agent_identities table
    op.create_table(
        "agent_identities",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("agent_id", sa.String(length=36), nullable=False),
        sa.Column("subject", sa.String(length=128), nullable=False),
        sa.Column("allowed_audiences", sa.JSON(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("org_id", "agent_id", name="uq_agent_identities_org_agent"),
    )
    op.create_index(op.f("ix_agent_identities_agent_id"), "agent_identities", ["agent_id"], unique=False)
    op.create_index(op.f("ix_agent_identities_org_id"), "agent_identities", ["org_id"], unique=False)
    op.create_index(op.f("ix_agent_identities_subject"), "agent_identities", ["subject"], unique=True)

    # 2. Create external_agents table
    op.create_table(
        "external_agents",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("agent_card_url", sa.String(length=512), nullable=False),
        sa.Column("auth_config", sa.JSON(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("org_id", "name", name="uq_external_agents_org_name"),
    )
    op.create_index(op.f("ix_external_agents_org_id"), "external_agents", ["org_id"], unique=False)

    # 3. Add a2a_exposed to agents table
    op.add_column(
        "agents",
        sa.Column("a2a_exposed", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    # 4. Add identity and delegation columns to audit_logs table
    op.add_column(
        "audit_logs",
        sa.Column("actor_agent_identity_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "audit_logs",
        sa.Column("delegation_chain", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("audit_logs", "delegation_chain")
    op.drop_column("audit_logs", "actor_agent_identity_id")
    op.drop_column("agents", "a2a_exposed")
    op.drop_index(op.f("ix_external_agents_org_id"), table_name="external_agents")
    op.drop_table("external_agents")
    op.drop_index(op.f("ix_agent_identities_subject"), table_name="agent_identities")
    op.drop_index(op.f("ix_agent_identities_org_id"), table_name="agent_identities")
    op.drop_index(op.f("ix_agent_identities_agent_id"), table_name="agent_identities")
    op.drop_table("agent_identities")
