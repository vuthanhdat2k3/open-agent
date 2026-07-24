"""add evaluation suites and experiment results

Revision ID: 0011_add_evaluation_framework
Revises: 0010_add_agent_releases
Create Date: 2026-07-24
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0011_add_evaluation_framework"
down_revision: str | None = "0010_add_agent_releases"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "evaluation_suites",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("agent_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.String(length=512), nullable=False),
        sa.Column("dataset_version", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("org_id", "name", name="uq_evaluation_suites_org_name"),
    )
    op.create_index("ix_evaluation_suites_agent_id", "evaluation_suites", ["agent_id"])
    op.create_index("ix_evaluation_suites_org_id", "evaluation_suites", ["org_id"])

    op.create_table(
        "evaluation_cases",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("suite_id", sa.String(length=36), nullable=False),
        sa.Column("input", sa.Text(), nullable=False),
        sa.Column("expected_output", sa.Text(), nullable=True),
        sa.Column("required_substrings", sa.JSON(), nullable=False),
        sa.Column("expected_tools", sa.JSON(), nullable=False),
        sa.Column("forbidden_patterns", sa.JSON(), nullable=False),
        sa.Column("max_latency_ms", sa.Integer(), nullable=True),
        sa.Column("max_cost_usd", sa.Float(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("added_in_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["suite_id"], ["evaluation_suites.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("suite_id", "ordinal", name="uq_evaluation_cases_suite_ordinal"),
    )
    op.create_index("ix_evaluation_cases_org_id", "evaluation_cases", ["org_id"])
    op.create_index("ix_evaluation_cases_suite_id", "evaluation_cases", ["suite_id"])

    op.create_table(
        "evaluation_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("suite_id", sa.String(length=36), nullable=False),
        sa.Column("agent_release_id", sa.String(length=36), nullable=False),
        sa.Column("baseline_run_id", sa.String(length=36), nullable=True),
        sa.Column("dataset_version", sa.Integer(), nullable=False),
        sa.Column("execution_mode", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("total_cases", sa.Integer(), nullable=False),
        sa.Column("passed_cases", sa.Integer(), nullable=False),
        sa.Column("pass_rate", sa.Float(), nullable=False),
        sa.Column("average_latency_ms", sa.Float(), nullable=False),
        sa.Column("total_cost_usd", sa.Float(), nullable=False),
        sa.Column("triggered_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["agent_release_id"], ["agent_releases.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["baseline_run_id"], ["evaluation_runs.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["suite_id"], ["evaluation_suites.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["triggered_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_evaluation_runs_agent_release_id",
        "evaluation_runs",
        ["agent_release_id"],
    )
    op.create_index("ix_evaluation_runs_org_id", "evaluation_runs", ["org_id"])
    op.create_index("ix_evaluation_runs_status", "evaluation_runs", ["status"])
    op.create_index("ix_evaluation_runs_suite_id", "evaluation_runs", ["suite_id"])

    op.create_table(
        "evaluation_results",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("case_id", sa.String(length=36), nullable=False),
        sa.Column("output", sa.Text(), nullable=False),
        sa.Column("observed_tools", sa.JSON(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("cost_usd", sa.Float(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("grader_details", sa.JSON(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["case_id"], ["evaluation_cases.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["run_id"], ["evaluation_runs.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "case_id", name="uq_evaluation_results_run_case"),
    )
    op.create_index("ix_evaluation_results_case_id", "evaluation_results", ["case_id"])
    op.create_index("ix_evaluation_results_org_id", "evaluation_results", ["org_id"])
    op.create_index("ix_evaluation_results_run_id", "evaluation_results", ["run_id"])


def downgrade() -> None:
    op.drop_index("ix_evaluation_results_run_id", table_name="evaluation_results")
    op.drop_index("ix_evaluation_results_org_id", table_name="evaluation_results")
    op.drop_index("ix_evaluation_results_case_id", table_name="evaluation_results")
    op.drop_table("evaluation_results")
    op.drop_index("ix_evaluation_runs_suite_id", table_name="evaluation_runs")
    op.drop_index("ix_evaluation_runs_status", table_name="evaluation_runs")
    op.drop_index("ix_evaluation_runs_org_id", table_name="evaluation_runs")
    op.drop_index(
        "ix_evaluation_runs_agent_release_id", table_name="evaluation_runs"
    )
    op.drop_table("evaluation_runs")
    op.drop_index("ix_evaluation_cases_suite_id", table_name="evaluation_cases")
    op.drop_index("ix_evaluation_cases_org_id", table_name="evaluation_cases")
    op.drop_table("evaluation_cases")
    op.drop_index("ix_evaluation_suites_org_id", table_name="evaluation_suites")
    op.drop_index("ix_evaluation_suites_agent_id", table_name="evaluation_suites")
    op.drop_table("evaluation_suites")
