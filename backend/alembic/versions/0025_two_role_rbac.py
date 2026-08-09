"""Collapse the 4-role model (owner/admin/developer/viewer) to 2 roles (admin/user).

Revision ID: 0025_two_role_rbac
Revises: 0024_ci_drive
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0025_two_role_rbac"
down_revision = "0024_ci_drive"
branch_labels = None
depends_on = None

OLD_ROLES = sa.Enum("owner", "admin", "developer", "viewer", name="role")


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # Postgres enums can't hold "user" until the column stops being that
        # native enum type, so widen to text first, then rewrite values.
        op.execute("ALTER TABLE memberships ALTER COLUMN role DROP DEFAULT")
        op.execute("ALTER TABLE memberships ALTER COLUMN role TYPE VARCHAR(32) USING role::text")
        op.execute("ALTER TABLE memberships ALTER COLUMN role SET DEFAULT 'user'")
        op.execute("DROP TYPE role")
    else:
        # SQLite has no native enum type to drop; batch mode rebuilds the
        # table so the new column carries no leftover CHECK constraint tied
        # to the old 4 values.
        with op.batch_alter_table("memberships") as batch_op:
            batch_op.alter_column(
                "role",
                existing_type=OLD_ROLES,
                type_=sa.String(length=32),
                existing_nullable=False,
                server_default="user",
            )

    op.execute("UPDATE memberships SET role = 'admin' WHERE role = 'owner'")
    op.execute("UPDATE memberships SET role = 'user' WHERE role = 'developer' OR role = 'viewer'")


def downgrade() -> None:
    # Lossy: the 4-role distinction (which admins were owners, which users
    # were developers vs viewers) no longer exists in the data. Best-effort
    # mapping only - admin stays admin, user becomes developer (the old
    # default role).
    op.execute("UPDATE memberships SET role = 'developer' WHERE role = 'user'")

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        OLD_ROLES.create(bind, checkfirst=True)
        op.execute("ALTER TABLE memberships ALTER COLUMN role DROP DEFAULT")
        op.execute("ALTER TABLE memberships ALTER COLUMN role TYPE role USING role::role")
        op.execute("ALTER TABLE memberships ALTER COLUMN role SET DEFAULT 'developer'")
    else:
        with op.batch_alter_table("memberships") as batch_op:
            batch_op.alter_column(
                "role",
                existing_type=sa.String(length=32),
                type_=OLD_ROLES,
                existing_nullable=False,
                server_default="developer",
            )
