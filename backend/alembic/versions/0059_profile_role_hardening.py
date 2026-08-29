"""Profile/role hardening: force-change-password flag + drop legacy admin alias.

- users.must_change_password: set on admin-chosen initial passwords so the UI
  forces a self-chosen password before unlocking.
- memberships.role: normalize the legacy ``admin`` spelling to ``org_admin``;
  the Role enum no longer contains ``admin``.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0059_profile_role_hardening"
down_revision: str | None = "0058_scope_workflow_name_unique_to_user"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "must_change_password",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.execute("UPDATE memberships SET role = 'org_admin' WHERE role = 'admin'")


def downgrade() -> None:
    # The admin->org_admin normalization is intentionally not reversible:
    # the Role enum no longer accepts the legacy spelling.
    op.drop_column("users", "must_change_password")
