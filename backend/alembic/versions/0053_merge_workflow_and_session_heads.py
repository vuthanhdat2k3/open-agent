"""Merge workflow parameter and session event migration branches."""

from collections.abc import Sequence

revision: str = "0053_merge_workflow_and_session_heads"
down_revision: str | tuple[str, str] | None = (
    "0051_workflow_parameters_backfill",
    "0052_session_events",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
