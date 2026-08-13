"""Add shadow-mode trusted calendar rules and automation budgets."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0035_trusted_rules"
down_revision = "0034_email_routing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ci_trusted_rules",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("org_id", sa.String(36), nullable=False),
        sa.Column("created_by_user_id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(24), nullable=False, server_default="ACTIVE"),
        sa.Column("match_type", sa.String(24), nullable=False),
        sa.Column("match_value", sa.String(320), nullable=False),
        sa.Column("action_type", sa.String(48), nullable=False, server_default="CALENDAR_AUTO_CREATE"),
        sa.Column("calendar_connection_id", sa.String(36), nullable=True),
        sa.Column("conditions", sa.JSON(), nullable=False),
        sa.Column("policy_version", sa.String(64), nullable=False, server_default="2026-08-13.1"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["calendar_connection_id"], ["ci_calendar_connections.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("org_id", "name", "version", name="uq_ci_trusted_rule_version"),
    )
    op.create_index("ix_ci_trusted_rules_org_id", "ci_trusted_rules", ["org_id"])
    op.create_index("ix_ci_trusted_rules_created_by_user_id", "ci_trusted_rules", ["created_by_user_id"])
    op.create_index("ix_ci_trusted_rules_status", "ci_trusted_rules", ["status"])
    op.create_table(
        "ci_public_email_domains",
        sa.Column("domain", sa.String(255), primary_key=True),
        sa.Column("registry_version", sa.String(64), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.bulk_insert(
        sa.table(
            "ci_public_email_domains",
            sa.column("domain", sa.String),
            sa.column("registry_version", sa.String),
            sa.column("enabled", sa.Boolean),
            sa.column("updated_at", sa.DateTime),
        ),
        [
            {"domain": domain, "registry_version": "2026-08-13.1", "enabled": True, "updated_at": sa.func.now()}
            for domain in ("gmail.com", "outlook.com", "hotmail.com", "yahoo.com", "protonmail.com", "icloud.com", "zoho.com", "mail.ru")
        ],
    )
    op.create_table(
        "ci_automation_budgets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scope_type", sa.String(16), nullable=False),
        sa.Column("scope_id", sa.String(36), nullable=False),
        sa.Column("budget_date", sa.String(10), nullable=False),
        sa.Column("used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("budget_limit", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("scope_type", "scope_id", "budget_date", name="uq_ci_automation_budget_scope_date"),
    )


def downgrade() -> None:
    op.drop_table("ci_automation_budgets")
    op.drop_table("ci_public_email_domains")
    op.drop_index("ix_ci_trusted_rules_status", table_name="ci_trusted_rules")
    op.drop_index("ix_ci_trusted_rules_created_by_user_id", table_name="ci_trusted_rules")
    op.drop_index("ix_ci_trusted_rules_org_id", table_name="ci_trusted_rules")
    op.drop_table("ci_trusted_rules")
