"""Cleanup unowned legacy workflows so workflows only exist per user."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0057_cleanup_unowned_workflows"
down_revision: str | None = "0056_repair_materialized_workflow_bindings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()
    # Delete legacy workflow records that have no owner (they exist as templates in the Marketplace)
    conn.execute(sa.text("DELETE FROM workflows WHERE created_by_user_id IS NULL"))


def downgrade() -> None:
    pass
