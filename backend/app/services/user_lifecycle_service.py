"""Account soft-delete: deactivate the user and disconnect their integrations.

Deleting an identity is owned by ZITADEL; the app-side counterpart is a soft
delete (is_active/lifecycle_status -> inactive) plus a full disconnect of the
customer-intelligence connections the account created. Disconnecting (revoke
+ clear credentials) matters even though the rows are org-scoped: the
UNIQUE (org_id, account_email) constraint would otherwise block the same
mailbox from being connected again later by whoever inherits it.
"""

from datetime import datetime, timezone

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.observability.audit import log_action
from app.customer_intelligence.oauth import revoke_provider_token
from app.customer_intelligence.security import decrypt_credentials
from app.models.customer_intelligence import (
    CalendarConnection,
    CiSchedule,
    DriveConnection,
    EmailConnection,
)
from app.models.membership import Membership
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.repositories.customer_intelligence import (
    CalendarConnectionRepository,
    DriveConnectionRepository,
    EmailConnectionRepository,
)

logger = structlog.get_logger(__name__)


class UserLifecycleService:
    """Soft-delete accounts: active -> inactive with full integration cleanup."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def deactivate_everywhere(
        self, *, user_id: str, actor_user_id: str | None = None
    ) -> bool:
        """Deactivate the account across every org and disconnect the
        integrations it created. Returns False when the user does not exist."""
        user = (
            await self.db.execute(select(User).where(User.id == user_id))
        ).scalar_one_or_none()
        if user is None:
            return False

        now = datetime.now(timezone.utc)
        user.is_active = False
        user.lifecycle_status = "inactive"

        await self.db.execute(
            update(Membership)
            .where(Membership.user_id == user_id)
            .values(lifecycle_status="inactive")
        )
        await self.db.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=now)
        )

        await self._disconnect_email(user_id, actor_user_id)
        await self._disconnect_calendar(user_id, actor_user_id)
        await self._disconnect_drive(user_id, actor_user_id)

        await self.db.commit()
        return True

    async def _disconnect_email(self, user_id: str, actor_user_id: str | None) -> None:
        repo = EmailConnectionRepository(self.db)
        rows = (
            await self.db.execute(
                select(EmailConnection).where(
                    EmailConnection.created_by_user_id == user_id,
                    EmailConnection.status == "connected",
                )
            )
        ).scalars().all()
        for conn in rows:
            await self._revoke_email_credentials(conn)
            await repo.update(conn, {"status": "disconnected", "credentials_enc": None})
            await self.db.execute(
                update(CiSchedule)
                .where(CiSchedule.connection_id == conn.id)
                .values(enabled=False)
            )
            await log_action(
                self.db,
                org_id=conn.org_id,
                actor_user_id=actor_user_id,
                action="ci.connection.disconnected",
                resource_type="ci_connection",
                resource_id=conn.id,
                metadata={"reason": "owner deactivated"},
            )

    async def _disconnect_calendar(self, user_id: str, actor_user_id: str | None) -> None:
        repo = CalendarConnectionRepository(self.db)
        rows = (
            await self.db.execute(
                select(CalendarConnection).where(
                    CalendarConnection.created_by_user_id == user_id,
                    CalendarConnection.status == "connected",
                )
            )
        ).scalars().all()
        for conn in rows:
            await self._revoke_google_credentials(conn)
            await repo.update(conn, {"status": "disconnected", "credentials_enc": None})
            await log_action(
                self.db,
                org_id=conn.org_id,
                actor_user_id=actor_user_id,
                action="ci.connection.disconnected",
                resource_type="ci_calendar_connection",
                resource_id=conn.id,
                metadata={"reason": "owner deactivated"},
            )

    async def _disconnect_drive(self, user_id: str, actor_user_id: str | None) -> None:
        repo = DriveConnectionRepository(self.db)
        rows = (
            await self.db.execute(
                select(DriveConnection).where(
                    DriveConnection.created_by_user_id == user_id,
                    DriveConnection.status == "connected",
                )
            )
        ).scalars().all()
        for conn in rows:
            await self._revoke_google_credentials(conn)
            await repo.update(conn, {"status": "disconnected", "credentials_enc": None})
            await log_action(
                self.db,
                org_id=conn.org_id,
                actor_user_id=actor_user_id,
                action="ci.connection.disconnected",
                resource_type="ci_drive_connection",
                resource_id=conn.id,
                metadata={"reason": "owner deactivated"},
            )

    async def _revoke_email_credentials(self, conn: EmailConnection) -> None:
        if not conn.credentials_enc:
            return
        from app.customer_intelligence.providers.email import get_email_provider
        from app.customer_intelligence.security import decrypt_credentials

        try:
            provider = get_email_provider(conn.provider)
            await provider.revoke(decrypt_credentials(conn.credentials_enc))
        except Exception:  # noqa: BLE001 - revoke is best-effort, same as the manual disconnect flow
            logger.warning("email token revoke failed", connection_id=conn.id)

    async def _revoke_google_credentials(self, conn) -> None:
        if not conn.credentials_enc:
            return
        try:
            await revoke_provider_token("google", decrypt_credentials(conn.credentials_enc))
        except Exception:  # noqa: BLE001
            logger.warning("google token revoke failed", connection_id=conn.id)
