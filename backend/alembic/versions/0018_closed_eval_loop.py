"""closed eval loop: sampling policies, case provenance, retrieval scoring

Everything here is additive with a default, so existing suites keep grading
exactly as they did under M11: cases default to source="manual" and
approved=True, releases to quality_gate_status="unknown".

Revision ID: 0018_closed_eval_loop
Revises: 0017_durable_execution
Create Date: 2026-08-02
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0018_closed_eval_loop"
down_revision: str | None = "0017_durable_execution"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sampling_policies",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "org_id",
            sa.String(length=36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "agent_id",
            sa.String(length=36),
            sa.ForeignKey("agents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "suite_id",
            sa.String(length=36),
            sa.ForeignKey("evaluation_suites.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("reasons", sa.JSON(), nullable=True),
        sa.Column("max_per_day", sa.Integer(), nullable=False, server_default="10"),
        sa.Column(
            "created_by_user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("org_id", "agent_id", "suite_id", name="uq_sampling_policy_target"),
    )
    op.create_index("ix_sampling_policies_org_id", "sampling_policies", ["org_id"])
    op.create_index("ix_sampling_policies_agent_id", "sampling_policies", ["agent_id"])

    # Provenance: existing rows were authored by hand, hence the defaults.
    op.add_column(
        "evaluation_cases",
        sa.Column("source", sa.String(length=16), nullable=False, server_default="manual"),
    )
    op.add_column(
        "evaluation_cases", sa.Column("source_run_ref", sa.String(length=64), nullable=True)
    )
    op.add_column(
        "evaluation_cases", sa.Column("sampled_reason", sa.String(length=64), nullable=True)
    )
    op.add_column(
        "evaluation_cases",
        sa.Column("approved", sa.Boolean(), nullable=False, server_default=sa.true()),
    )

    # Retrieval expectations.
    op.add_column("evaluation_cases", sa.Column("expected_doc_ids", sa.JSON(), nullable=True))
    op.add_column("evaluation_cases", sa.Column("min_recall_at_k", sa.Float(), nullable=True))
    op.add_column("evaluation_cases", sa.Column("retrieval_k", sa.Integer(), nullable=True))
    op.add_column("evaluation_cases", sa.Column("min_groundedness", sa.Float(), nullable=True))

    op.add_column("evaluation_results", sa.Column("retrieved_doc_ids", sa.JSON(), nullable=True))

    op.add_column(
        "agent_releases",
        sa.Column(
            "quality_gate_status", sa.String(length=16), nullable=False, server_default="unknown"
        ),
    )
    op.add_column(
        "agent_releases", sa.Column("quality_gate_run_id", sa.String(length=36), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("agent_releases", "quality_gate_run_id")
    op.drop_column("agent_releases", "quality_gate_status")

    op.drop_column("evaluation_results", "retrieved_doc_ids")

    op.drop_column("evaluation_cases", "min_groundedness")
    op.drop_column("evaluation_cases", "retrieval_k")
    op.drop_column("evaluation_cases", "min_recall_at_k")
    op.drop_column("evaluation_cases", "expected_doc_ids")
    op.drop_column("evaluation_cases", "approved")
    op.drop_column("evaluation_cases", "sampled_reason")
    op.drop_column("evaluation_cases", "source_run_ref")
    op.drop_column("evaluation_cases", "source")

    op.drop_index("ix_sampling_policies_agent_id", table_name="sampling_policies")
    op.drop_index("ix_sampling_policies_org_id", table_name="sampling_policies")
    op.drop_table("sampling_policies")
