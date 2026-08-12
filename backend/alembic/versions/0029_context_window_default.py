"""Use 138000 as the generic model context window default."""

from collections.abc import Sequence

from alembic import op

revision: str = "0029_context_window_default"
down_revision: str | None = "0028_provider_discovery"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE models
        SET context_window = 138000
        WHERE source = 'discovered' AND context_window = 8192
        """
    )


def downgrade() -> None:
    # This data migration intentionally does not reverse values: after upgrade,
    # a 138000 value may be an explicit user/provider choice.
    pass
