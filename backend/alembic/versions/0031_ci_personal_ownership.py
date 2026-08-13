"""Scope Customer Intelligence emails and cases to their connector owner."""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0031_ci_personal_ownership"
down_revision = "0030_job_scheduling_hardening"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Batch mode rebuilds the table on SQLite and emits ALTER COLUMN on
    # PostgreSQL, so the same migration works for local tests and production.
    with op.batch_alter_table("ci_emails", recreate="auto") as batch_op:
        batch_op.alter_column(
            "connection_id", existing_type=sa.String(length=36), nullable=True
        )
    with op.batch_alter_table("ci_emails", recreate="auto") as batch_op:
        batch_op.add_column(sa.Column("created_by_user_id", sa.String(length=36), nullable=True))
        batch_op.create_index("ix_ci_emails_created_by_user_id", ["created_by_user_id"])
        batch_op.create_foreign_key(
            "fk_ci_emails_created_by_user_id", "users", ["created_by_user_id"], ["id"], ondelete="SET NULL"
        )
    with op.batch_alter_table("ci_cases", recreate="auto") as batch_op:
        batch_op.add_column(sa.Column("created_by_user_id", sa.String(length=36), nullable=True))
        batch_op.create_index("ix_ci_cases_created_by_user_id", ["created_by_user_id"])
        batch_op.create_foreign_key(
            "fk_ci_cases_created_by_user_id", "users", ["created_by_user_id"], ["id"], ondelete="SET NULL"
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
    with op.batch_alter_table("ci_cases", recreate="auto") as batch_op:
        batch_op.drop_constraint("fk_ci_cases_created_by_user_id", type_="foreignkey")
        batch_op.drop_index("ix_ci_cases_created_by_user_id")
        batch_op.drop_column("created_by_user_id")
    with op.batch_alter_table("ci_emails", recreate="auto") as batch_op:
        batch_op.drop_constraint("fk_ci_emails_created_by_user_id", type_="foreignkey")
        batch_op.drop_index("ix_ci_emails_created_by_user_id")
        batch_op.drop_column("created_by_user_id")
