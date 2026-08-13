"""Scope Customer Intelligence emails and cases to their connector owner."""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0031_ci_personal_ownership"
down_revision = "0030_job_scheduling_hardening"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("ci_emails", "connection_id", existing_type=sa.String(length=36), nullable=True)
    op.add_column(
        "ci_emails",
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
    )
    op.create_index("ix_ci_emails_created_by_user_id", "ci_emails", ["created_by_user_id"])
    op.create_foreign_key(
        "fk_ci_emails_created_by_user_id",
        "ci_emails",
        "users",
        ["created_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column(
        "ci_cases",
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
    )
    op.create_index("ix_ci_cases_created_by_user_id", "ci_cases", ["created_by_user_id"])
    op.create_foreign_key(
        "fk_ci_cases_created_by_user_id",
        "ci_cases",
        "users",
        ["created_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.execute(
        sa.text(
            """
            UPDATE ci_emails AS e
            SET created_by_user_id = c.created_by_user_id
            FROM ci_connections AS c
            WHERE e.connection_id = c.id
              AND e.created_by_user_id IS NULL
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE ci_cases AS ca
            SET created_by_user_id = e.created_by_user_id
            FROM ci_emails AS e
            WHERE ca.email_id = e.id
              AND ca.created_by_user_id IS NULL
            """
        )
    )


def downgrade() -> None:
    op.drop_constraint("fk_ci_cases_created_by_user_id", "ci_cases", type_="foreignkey")
    op.drop_index("ix_ci_cases_created_by_user_id", table_name="ci_cases")
    op.drop_column("ci_cases", "created_by_user_id")
    op.drop_constraint("fk_ci_emails_created_by_user_id", "ci_emails", type_="foreignkey")
    op.drop_index("ix_ci_emails_created_by_user_id", table_name="ci_emails")
    op.drop_column("ci_emails", "created_by_user_id")
