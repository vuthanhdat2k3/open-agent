"""Add the platform control-plane role to the application role vocabulary."""

from collections.abc import Sequence

revision: str = "0048_platform_admin_role"
down_revision: str | None = "0047_service_principals"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Membership roles are persisted as VARCHAR (native_enum=False); the
    # Python enum is the single source of truth and needs no DB type change.
    pass


def downgrade() -> None:
    pass
