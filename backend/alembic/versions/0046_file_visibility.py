"""Make uploaded-file visibility explicit for tenant and owner enforcement."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0046_file_visibility"
down_revision: str | None = "0045_identity_sessions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("uploaded_files") as batch:
        batch.add_column(sa.Column("visibility", sa.String(length=16), server_default="personal", nullable=False))


def downgrade() -> None:
    with op.batch_alter_table("uploaded_files") as batch:
        batch.drop_column("visibility")
