"""Persist agent classification output for audit and cache reuse."""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0037_agent_classification"
down_revision = "0036_smart_inbox_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ci_emails", sa.Column("classification_json", sa.JSON(), nullable=True))
    op.add_column(
        "ci_emails", sa.Column("classification_started_at", sa.DateTime(), nullable=True)
    )
    op.create_table(
        "ci_connection_cutovers",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("connection_id", sa.String(length=36), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("cutover_history_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("deleted_counts", sa.JSON(), nullable=False),
        sa.Column("actor", sa.String(length=128), nullable=False),
        sa.Column("cutover_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["connection_id"], ["ci_connections.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "connection_id", "generation", name="uq_ci_cutover_connection_generation"
        ),
        sa.UniqueConstraint("org_id", "idempotency_key", name="uq_ci_cutover_org_idempotency"),
    )
    op.create_index(
        "ix_ci_connection_cutovers_connection_id",
        "ci_connection_cutovers",
        ["connection_id"],
    )
    op.create_index(
        "ix_ci_connection_cutovers_org_id", "ci_connection_cutovers", ["org_id"]
    )
    op.create_table(
        "ci_classification_cache",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("cache_key", sa.String(length=64), nullable=False),
        sa.Column("model_id", sa.String(length=36), nullable=False),
        sa.Column("result_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("org_id", "cache_key", name="uq_ci_classification_cache_key"),
    )
    op.create_index(
        "ix_ci_classification_cache_org_id", "ci_classification_cache", ["org_id"]
    )
    op.create_index(
        "ix_ci_cases_org_status_created", "ci_cases", ["org_id", "status", "created_at"]
    )
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            "CREATE INDEX ix_ci_cases_company_name_trgm ON ci_cases "
            "USING gin (company_name gin_trgm_ops)"
        )
        op.execute(
            "CREATE INDEX ix_ci_cases_company_domain_trgm ON ci_cases "
            "USING gin (company_domain gin_trgm_ops)"
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP INDEX IF EXISTS ix_ci_cases_company_domain_trgm")
        op.execute("DROP INDEX IF EXISTS ix_ci_cases_company_name_trgm")
    op.drop_index("ix_ci_cases_org_status_created", table_name="ci_cases")
    op.drop_index("ix_ci_classification_cache_org_id", table_name="ci_classification_cache")
    op.drop_table("ci_classification_cache")
    op.drop_index("ix_ci_connection_cutovers_org_id", table_name="ci_connection_cutovers")
    op.drop_index(
        "ix_ci_connection_cutovers_connection_id", table_name="ci_connection_cutovers"
    )
    op.drop_table("ci_connection_cutovers")
    op.drop_column("ci_emails", "classification_started_at")
    op.drop_column("ci_emails", "classification_json")
