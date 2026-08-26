"""Add session_events append-only conversation log."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0052_session_events"
down_revision: str | None = "0050_automation_template_dag_graphs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "session_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "org_id",
            sa.String(36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("session_id", sa.String(36), sa.ForeignKey("sessions.id"), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(64), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_session_events_session_seq",
        "session_events",
        ["session_id", "seq"],
        unique=True,
    )
    op.create_index(
        "ix_session_events_org_session",
        "session_events",
        ["org_id", "session_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_session_events_org_session", table_name="session_events")
    op.drop_index("ix_session_events_session_seq", table_name="session_events")
    op.drop_table("session_events")
