"""Add service principals and fixed product-key scopes."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0047_service_principals"
down_revision: str | None = "0046_file_visibility"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "service_principals",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("permissions", sa.JSON(), nullable=False),
        sa.Column("lifecycle_status", sa.String(length=24), server_default="active", nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_service_principals_org_id", "service_principals", ["org_id"])
    with op.batch_alter_table("api_keys") as batch:
        batch.add_column(sa.Column("service_principal_id", sa.String(length=36), nullable=True))
        batch.add_column(sa.Column("scopes", sa.JSON(), server_default="[]", nullable=False))
        batch.create_foreign_key(
            "fk_api_keys_service_principal_id", "service_principals", ["service_principal_id"], ["id"], ondelete="CASCADE"
        )
        batch.create_index("ix_api_keys_service_principal_id", ["service_principal_id"])


def downgrade() -> None:
    with op.batch_alter_table("api_keys") as batch:
        batch.drop_index("ix_api_keys_service_principal_id")
        batch.drop_constraint("fk_api_keys_service_principal_id", type_="foreignkey")
        batch.drop_column("scopes")
        batch.drop_column("service_principal_id")
    op.drop_index("ix_service_principals_org_id", table_name="service_principals")
    op.drop_table("service_principals")
