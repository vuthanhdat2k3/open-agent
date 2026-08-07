from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.observability.audit import log_action
from app.customer_intelligence.providers.email import get_email_provider
from app.customer_intelligence.security import (
    decrypt_credentials,
    encrypt_credentials,
    redact_oauth_payload,
)
from app.models.customer_intelligence import EmailConnection
from app.repositories.customer_intelligence import EmailConnectionRepository
from app.schemas.customer_intelligence import ConnectionResponse


class CustomerIntelligenceService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.connections = EmailConnectionRepository(db)

    def _to_response(self, conn: EmailConnection) -> ConnectionResponse:
        return ConnectionResponse(
            id=conn.id,
            provider=conn.provider,
            account_email=conn.account_email,
            status=conn.status,
            error=conn.error,
            has_credentials=bool(conn.credentials_enc),
            last_sync_at=conn.last_sync_at,
            created_at=conn.created_at,
        )

    async def connect(
        self,
        *,
        org_id: str,
        provider: str,
        account_email: str,
        oauth_payload: dict[str, Any],
        created_by_user_id: str | None = None,
    ) -> ConnectionResponse:
        conn = await self.connections.get_by_account(org_id, account_email)
        if conn is None:
            conn = EmailConnection(
                org_id=org_id,
                provider=provider,
                account_email=account_email,
                status="connected",
            )
            conn.credentials_enc = encrypt_credentials(oauth_payload)
            conn.created_by_user_id = created_by_user_id
            await self.connections.create(conn)
        else:
            await self.connections.update(
                conn,
                {
                    "provider": provider,
                    "status": "connected",
                    "error": None,
                    "credentials_enc": encrypt_credentials(oauth_payload),
                },
            )
        await log_action(
            self.db,
            org_id=org_id,
            actor_user_id=created_by_user_id,
            action="ci.connection.connected",
            resource_type="ci_connection",
            resource_id=conn.id,
            metadata={"provider": provider, "account_email": account_email},
        )
        return self._to_response(conn)

    async def disconnect(
        self, *, org_id: str, connection_id: str, actor_user_id: str | None = None
    ) -> ConnectionResponse | None:
        conn = await self.connections.get(org_id, connection_id)
        if conn is None:
            return None
        provider = get_email_provider(conn.provider)
        try:
            await provider.revoke(decrypt_credentials(conn.credentials_enc or "{}"))
        except Exception:  # noqa: BLE001
            pass
        await self.connections.update(conn, {"status": "disconnected", "credentials_enc": None})
        await log_action(
            self.db,
            org_id=org_id,
            actor_user_id=actor_user_id,
            action="ci.connection.disconnected",
            resource_type="ci_connection",
            resource_id=connection_id,
        )
        return self._to_response(conn)

    async def status(self, *, org_id: str) -> list[ConnectionResponse]:
        conns = await self.connections.list(org_id)
        return [self._to_response(c) for c in conns]

    async def get_credentials(
        self, *, org_id: str, connection_id: str
    ) -> tuple[EmailConnection, dict[str, Any]] | None:
        conn = await self.connections.get(org_id, connection_id)
        if conn is None or not conn.credentials_enc:
            return None
        return conn, decrypt_credentials(conn.credentials_enc)

    async def refresh_token(self, *, org_id: str, connection_id: str) -> bool:
        """Refresh the OAuth access token through the provider adapter.
        The refreshed payload is re-encrypted at rest. Returns True when a
        token was refreshed, False when the provider has nothing to refresh.
        """
        pair = await self.get_credentials(org_id=org_id, connection_id=connection_id)
        if pair is None:
            return False
        conn, creds = pair
        provider = get_email_provider(conn.provider)
        refreshed = await provider.refresh_access_token(creds)
        if refreshed:
            await self.connections.update(
                conn,
                {
                    "credentials_enc": encrypt_credentials(refreshed),
                    "status": "connected",
                    "error": None,
                },
            )
            redacted = redact_oauth_payload(refreshed)
            await log_action(
                self.db,
                org_id=org_id,
                action="ci.connection.token_refreshed",
                resource_type="ci_connection",
                resource_id=connection_id,
                metadata={"refreshed_fields": list(redacted.keys())},
            )
        return bool(refreshed)

    async def research_case(
        self, *, org_id: str, case_id: str, actor_user_id: str | None = None
    ) -> dict[str, Any]:
        """Run the research DAG for an INGESTED case and persist the briefing."""
        from app.customer_intelligence.workflow import run_research

        return await run_research(
            self.db,
            org_id=org_id,
            case_id=case_id,
            actor_user_id=actor_user_id,
        )

    async def propose_delivery(
        self,
        *,
        org_id: str,
        case_id: str,
        action: str,
        payload: dict[str, Any],
        requested_by: str | None = None,
    ):
        """Open an approval gate for a delivery side effect on a researched case."""
        from app.customer_intelligence.delivery import (
            DeliveryError,
            request_case_approval,
        )

        try:
            approval = await request_case_approval(
                self.db,
                org_id=org_id,
                case_id=case_id,
                action=action,
                payload=payload,
                requested_by=requested_by,
            )
        except DeliveryError as exc:
            raise ValueError(str(exc))
        return self._approval_out(approval)

    async def decide_delivery(
        self,
        *,
        org_id: str,
        approval_id: str,
        case_id: str | None = None,
        decision: str,
        decided_by: str | None = None,
        reason: str = "",
    ):
        """Decide a pending delivery approval and execute the side effect if approved."""
        from app.customer_intelligence.delivery import (
            DeliveryError,
            decide_case_approval,
        )

        try:
            approval = await decide_case_approval(
                self.db,
                org_id=org_id,
                approval_id=approval_id,
                expected_case_id=case_id,
                decision=decision,
                decided_by=decided_by,
                reason=reason,
            )
        except DeliveryError as exc:
            raise ValueError(str(exc))
        return self._approval_out(approval)

    async def get_case_approval(
        self, *, org_id: str, case_id: str
    ):
        """Return the latest approval request for a case (pending first), if any."""
        from sqlalchemy import select

        from app.models.approval_request import ApprovalRequest

        res = await self.db.execute(
            select(ApprovalRequest)
            .where(ApprovalRequest.org_id == org_id, ApprovalRequest.case_id == case_id)
            .order_by(ApprovalRequest.created_at.desc())
            .limit(1)
        )
        approval = res.scalar_one_or_none()
        return self._approval_out(approval) if approval else None

    @staticmethod
    def _approval_out(approval) -> dict[str, Any]:
        from app.schemas.customer_intelligence import ApprovalOut

        return ApprovalOut(
            id=approval.id,
            case_id=approval.case_id,
            action=approval.tool_name,
            status=approval.status,
            reason=approval.reason,
            requested_by=approval.requested_by,
            decided_by=approval.decided_by,
            decided_at=approval.decided_at,
            expires_at=approval.expires_at,
            args_snapshot=approval.args_snapshot,
            created_at=approval.created_at,
        )