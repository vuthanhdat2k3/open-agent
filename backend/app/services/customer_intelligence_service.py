from __future__ import annotations

from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.observability.audit import log_action
from app.customer_intelligence.providers.email import get_email_provider
from app.customer_intelligence.security import (
    decrypt_credentials,
    encrypt_credentials,
    redact_oauth_payload,
)
from app.db.base import utc_now
from app.models.customer_intelligence import EmailConnection
from app.repositories.customer_intelligence import EmailConnectionRepository
from app.schemas.customer_intelligence import ConnectionResponse

logger = structlog.get_logger(__name__)


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
            owner_id = (
                conn.created_by_user_id
                if conn.status == "connected" and conn.credentials_enc
                else created_by_user_id
            )
            await self.connections.update(
                conn,
                {
                    "provider": provider,
                    "status": "connected",
                    "error": None,
                    "credentials_enc": encrypt_credentials(oauth_payload),
                    "created_by_user_id": owner_id,
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

    async def status(self, *, org_id: str, created_by_user_id: str | None = None) -> list[ConnectionResponse]:
        conns = await self.connections.list(org_id, created_by_user_id=created_by_user_id)
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
        """Run research and schedule transient failures for retry."""
        from datetime import timedelta

        from app.core.scheduling.backoff import MAX_RETRY_COUNT, compute_backoff_seconds
        from app.customer_intelligence.workflow import ResearchError, run_research
        from app.repositories.customer_intelligence import ResearchCaseRepository

        repository = ResearchCaseRepository(self.db)
        if await repository.claim_for_research(org_id, case_id) is None:
            return {"case_id": case_id, "skipped": True}
        try:
            return await run_research(
                self.db,
                org_id=org_id,
                case_id=case_id,
                actor_user_id=actor_user_id,
            )
        except ResearchError:
            case = await repository.get(org_id, case_id)
            if case is not None and case.status == "RESEARCHING":
                case.error = "research rejected: invalid or incomplete case data"
                await repository.transition(case, "DEAD_LETTER")
            raise
        except Exception as exc:
            # This is intentionally broad: a network blip, a provider 5xx, or
            # a genuine programming bug all land here and are treated as
            # retryable up to MAX_RETRY_COUNT before dead-lettering. Logging
            # the full exception (not just swallowing it) means a real bug
            # is still visible in logs/traces well before the 5th retry.
            await logger.aerror(
                "research_case_failed_scheduling_retry",
                org_id=org_id,
                case_id=case_id,
                error=str(exc),
                exc_info=True,
            )
            case = await repository.get(org_id, case_id)
            if case is not None and case.status == "RESEARCHING":
                next_count = case.retry_count + 1
                if next_count > MAX_RETRY_COUNT:
                    case.error = "research retry limit exceeded"
                    await repository.transition(case, "DEAD_LETTER")
                else:
                    await repository.schedule_retry(
                        case,
                        next_retry_at=utc_now()
                        + timedelta(seconds=compute_backoff_seconds(case.retry_count)),
                        triggered_by=None,
                    )
            raise

    async def retry_case(self, *, org_id: str, case_id: str, actor_user_id: str):
        """Schedule a manual retry for a failed Customer Intelligence case."""
        from app.core.observability.metrics import ci_case_retry_total
        from app.repositories.customer_intelligence import ResearchCaseRepository

        repository = ResearchCaseRepository(self.db)
        case = await repository.get(org_id, case_id)
        if case is None:
            raise LookupError("case not found")
        if case.status not in {"RETRYING", "DEAD_LETTER", "NEEDS_REVIEW"}:
            raise ValueError(f"case cannot be retried from status={case.status}")
        previous_status = case.status
        if previous_status in {"DEAD_LETTER", "NEEDS_REVIEW"}:
            await repository.transition(case, "RETRYING")
        case = await repository.schedule_retry(
            case,
            next_retry_at=utc_now(),
            triggered_by=actor_user_id,
        )
        ci_case_retry_total.labels(trigger="manual", outcome="retried").inc()
        await log_action(
            self.db,
            org_id=org_id,
            actor_user_id=actor_user_id,
            action="ci.case.retry_triggered",
            resource_type="ci_case",
            resource_id=case_id,
            metadata={
                "trigger": "manual",
                "previous_status": previous_status,
                "retry_count": case.retry_count,
            },
        )
        return case

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
