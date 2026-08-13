"""Persist agent classification output for audit and cache reuse."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0037_agent_classification"
down_revision = "0036_smart_inbox_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ci_emails", sa.Column("classification_json", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("ci_emails", "classification_json")
