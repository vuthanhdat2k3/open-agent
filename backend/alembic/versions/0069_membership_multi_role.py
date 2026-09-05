"""Allow a user to hold more than one role in the same org.

Revision ID: 0069_membership_multi_role
Revises: 0068_channel_conversations
Create Date: 2026-09-05
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0069_membership_multi_role"
down_revision: str | None = "0068_channel_conversations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name == "postgresql":
        op.execute("ALTER TABLE memberships DROP CONSTRAINT IF EXISTS uq_membership_org_user")
        op.create_unique_constraint(
            "uq_membership_org_user_role", "memberships", ["org_id", "user_id", "role"]
        )
    else:
        # SQLite has no ALTER for constraints - batch mode copies the table.
        with op.batch_alter_table("memberships") as batch_op:
            batch_op.drop_constraint("uq_membership_org_user", type_="unique")
            batch_op.create_unique_constraint(
                "uq_membership_org_user_role", ["org_id", "user_id", "role"]
            )


def downgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name == "postgresql":
        op.execute("ALTER TABLE memberships DROP CONSTRAINT IF EXISTS uq_membership_org_user_role")
        op.create_unique_constraint("uq_membership_org_user", "memberships", ["org_id", "user_id"])
    else:
        with op.batch_alter_table("memberships") as batch_op:
            batch_op.drop_constraint("uq_membership_org_user_role", type_="unique")
            batch_op.create_unique_constraint("uq_membership_org_user", ["org_id", "user_id"])
