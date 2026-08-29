"""Profile/role hardening: force-change-password flag + drop legacy admin alias.

- users.must_change_password: set on admin-chosen initial passwords so the UI
  forces a self-chosen password before unlocking.
- memberships.role: normalize the legacy ``admin`` spelling to ``org_admin``;
  the Role enum no longer contains ``admin``.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0060_profile_role_hardening"
down_revision: str | None = "0059_org_agent_settings_and_template_key"
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
    # Normalize existing "admin" membership roles to the canonical "org_admin"
    # value now that Role.admin is dropped from the Python enum.
    op.execute(
        sa.text("UPDATE memberships SET role = 'org_admin' WHERE role = 'admin'")
    )


def downgrade() -> None:
    op.drop_column("users", "must_change_password")
