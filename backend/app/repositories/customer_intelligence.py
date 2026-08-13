from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utc_now
from app.models.customer_intelligence import (
    BriefingReport,
    CalendarConnection,
    CiSchedule,
    DeliveryAttempt,
    DriveConnection,
    EmailConnection,
    InboundEmail,
    Meeting,
    ResearchCase,
    ResearchSource,
)
from app.repositories.base import BaseRepository

CASE_TRANSITIONS: dict[str, set[str]] = {
    "NEW": {"INGESTED"},
    "INGESTED": {"RESEARCHING"},
    "RESEARCHING": {"REPORT_READY", "RETRYING", "DEAD_LETTER"},
    "REPORT_READY": {"AWAITING_APPROVAL"},
    "AWAITING_APPROVAL": {"APPROVED", "REJECTED", "EXPIRED"},
    "APPROVED": {"EXECUTING"},
    "EXECUTING": {"COMPLETED", "RETRYING"},
    "RETRYING": {"RESEARCHING", "EXECUTING", "DEAD_LETTER"},
    "DEAD_LETTER": {"RETRYING"},
}


class EmailConnectionRepository(BaseRepository[EmailConnection]):
    def __init__(self, db: AsyncSession):
        super().__init__(EmailConnection, db)

    async def get_by_account(self, org_id: str, account_email: str) -> EmailConnection | None:
        res = await self.db.execute(
            select(EmailConnection).where(
                EmailConnection.org_id == org_id,
                EmailConnection.account_email == account_email,
            )
        )
        return res.scalar_one_or_none()


    async def get_gmail_by_account(self, account_email: str) -> EmailConnection | None:
        res = await self.db.execute(
            select(EmailConnection).where(
                EmailConnection.provider == "gmail",
                EmailConnection.account_email == account_email.lower(),
                EmailConnection.status == "connected",
            )
        )
        return res.scalar_one_or_none()


class CalendarConnectionRepository(BaseRepository[CalendarConnection]):
    def __init__(self, db: AsyncSession):
        super().__init__(CalendarConnection, db)

    async def get_by_account(self, org_id: str, provider: str, account_email: str) -> CalendarConnection | None:
        res = await self.db.execute(
            select(CalendarConnection).where(
                CalendarConnection.org_id == org_id,
                CalendarConnection.provider == provider,
                CalendarConnection.account_email == account_email,
            )
        )
        return res.scalar_one_or_none()

    async def get_connected(self, org_id: str, user_id: str | None = None) -> CalendarConnection | None:
        filters = [CalendarConnection.org_id == org_id, CalendarConnection.status == "connected"]
        if user_id:
            filters.append(CalendarConnection.created_by_user_id == user_id)
        res = await self.db.execute(
            select(CalendarConnection)
            .where(*filters)
            .order_by(CalendarConnection.created_at.desc())
            .limit(1)
        )
        return res.scalar_one_or_none()


class DriveConnectionRepository(BaseRepository[DriveConnection]):
    def __init__(self, db: AsyncSession):
        super().__init__(DriveConnection, db)

    async def get_by_account(self, org_id: str, account_email: str) -> DriveConnection | None:
        res = await self.db.execute(
            select(DriveConnection).where(
                DriveConnection.org_id == org_id,
                DriveConnection.account_email == account_email,
            )
        )
        return res.scalar_one_or_none()


    async def get_connected(self, org_id: str, user_id: str | None = None) -> DriveConnection | None:
        filters = [DriveConnection.org_id == org_id, DriveConnection.status == "connected"]
        if user_id:
            filters.append(DriveConnection.created_by_user_id == user_id)
        res = await self.db.execute(
            select(DriveConnection)
            .where(*filters)
            .order_by(DriveConnection.created_at.desc())
            .limit(1)
        )
        return res.scalar_one_or_none()


class InboundEmailRepository(BaseRepository[InboundEmail]):
    def __init__(self, db: AsyncSession):
        super().__init__(InboundEmail, db)

    async def find_by_provider_message_id(
        self, org_id: str, provider: str, provider_message_id: str
    ) -> InboundEmail | None:
        res = await self.db.execute(
            select(InboundEmail).where(
                InboundEmail.org_id == org_id,
                InboundEmail.provider == provider,
                InboundEmail.provider_message_id == provider_message_id,
            )
        )
        return res.scalar_one_or_none()


class ResearchCaseRepository(BaseRepository[ResearchCase]):
    def __init__(self, db: AsyncSession):
        super().__init__(ResearchCase, db)

    async def get_by_email(self, org_id: str, email_id: str, created_by_user_id: str | None = None) -> ResearchCase | None:
        filters = [ResearchCase.org_id == org_id, ResearchCase.email_id == email_id]
        if created_by_user_id is not None:
            filters.append(ResearchCase.created_by_user_id == created_by_user_id)
        res = await self.db.execute(
            select(ResearchCase).where(*filters)
        )
        return res.scalar_one_or_none()

    async def list_by_status(
        self, org_id: str, status: str | None = None, limit: int = 100, offset: int = 0,
        created_by_user_id: str | None = None,
    ) -> list[ResearchCase]:
        stmt = select(ResearchCase).where(ResearchCase.org_id == org_id)
        if created_by_user_id is not None:
            stmt = stmt.where(ResearchCase.created_by_user_id == created_by_user_id)
        if status:
            stmt = stmt.where(ResearchCase.status == status)
        stmt = stmt.order_by(ResearchCase.created_at.desc()).limit(limit).offset(offset)
        res = await self.db.execute(stmt)
        return list(res.scalars().all())

    async def transition(self, case: ResearchCase, new_status: str) -> ResearchCase:
        allowed = CASE_TRANSITIONS.get(case.status, set())
        if new_status not in allowed:
            raise ValueError(f"illegal case transition: {case.status} -> {new_status}")
        case.status = new_status
        await self.db.commit()
        await self.db.refresh(case)
        return case

    async def claim_for_research(self, org_id: str, case_id: str) -> ResearchCase | None:
        """Atomically claim an INGESTED or due RETRYING case."""
        now = utc_now()
        stale_before = now - timedelta(minutes=30)
        result = await self.db.execute(
            update(ResearchCase)
            .where(
                ResearchCase.org_id == org_id,
                ResearchCase.id == case_id,
                or_(
                    ResearchCase.status == "INGESTED",
                    and_(
                        ResearchCase.status == "RETRYING",
                        ResearchCase.next_retry_at.is_not(None),
                        ResearchCase.next_retry_at <= now,
                    ),
                    and_(
                        ResearchCase.status == "RESEARCHING",
                        ResearchCase.started_at.is_not(None),
                        ResearchCase.started_at <= stale_before,
                    ),
                ),
            )
            .values(status="RESEARCHING", started_at=now, error=None)
        )
        if result.rowcount != 1:
            return None
        await self.db.commit()
        return await self.get(org_id, case_id)

    async def list_dispatchable(self, *, limit: int = 100) -> list[ResearchCase]:
        stale_before = utc_now() - timedelta(minutes=30)
        result = await self.db.execute(
            select(ResearchCase)
            .where(
                or_(
                    ResearchCase.status == "INGESTED",
                    and_(
                        ResearchCase.status == "RESEARCHING",
                        ResearchCase.started_at.is_not(None),
                        ResearchCase.started_at <= stale_before,
                    ),
                )
            )
            .order_by(ResearchCase.created_at)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def schedule_retry(
        self,
        case: ResearchCase,
        *,
        next_retry_at: datetime,
        triggered_by: str | None,
    ) -> ResearchCase:
        """Move a case into RETRYING and schedule its next attempt."""
        if case.status != "RETRYING":
            allowed = CASE_TRANSITIONS.get(case.status, set())
            if "RETRYING" not in allowed:
                raise ValueError(f"illegal case transition: {case.status} -> RETRYING")
            case.status = "RETRYING"
        case.retry_count += 1
        case.next_retry_at = next_retry_at
        case.last_retry_triggered_by = triggered_by
        case.error = None
        await self.db.commit()
        await self.db.refresh(case)
        return case

    async def list_due_for_retry(self, now: datetime, *, limit: int = 50) -> list[ResearchCase]:
        result = await self.db.execute(
            select(ResearchCase)
            .where(
                ResearchCase.status == "RETRYING",
                ResearchCase.next_retry_at.is_not(None),
                ResearchCase.next_retry_at <= now,
            )
            .order_by(ResearchCase.next_retry_at, ResearchCase.created_at)
            .limit(limit)
        )
        return list(result.scalars().all())


class ResearchSourceRepository(BaseRepository[ResearchSource]):
    def __init__(self, db: AsyncSession):
        super().__init__(ResearchSource, db)

    async def list_by_case(self, org_id: str, case_id: str) -> list[ResearchSource]:
        res = await self.db.execute(
            select(ResearchSource)
            .where(ResearchSource.org_id == org_id, ResearchSource.case_id == case_id)
            .order_by(ResearchSource.created_at)
        )
        return list(res.scalars().all())

    async def bulk_create(self, sources: list[ResearchSource]) -> None:
        if not sources:
            return
        org_id = sources[0].org_id
        case_id = sources[0].case_id
        existing_result = await self.db.execute(
            select(ResearchSource.url).where(
                ResearchSource.org_id == org_id,
                ResearchSource.case_id == case_id,
            )
        )
        existing_urls = set(existing_result.scalars().all())
        self.db.add_all([source for source in sources if source.url not in existing_urls])
        await self.db.commit()


class MeetingRepository(BaseRepository[Meeting]):
    def __init__(self, db: AsyncSession):
        super().__init__(Meeting, db)

    async def list_by_case(self, org_id: str, case_id: str) -> list[Meeting]:
        res = await self.db.execute(
            select(Meeting)
            .where(Meeting.org_id == org_id, Meeting.case_id == case_id)
            .order_by(Meeting.start_at)
        )
        return list(res.scalars().all())

    async def bulk_upsert(self, meetings: list[Meeting]) -> None:
        if not meetings:
            return
        org_id = meetings[0].org_id
        case_id = meetings[0].case_id
        event_ids = [meeting.provider_event_id for meeting in meetings]
        existing_result = await self.db.execute(
            select(Meeting.provider_event_id).where(
                Meeting.org_id == org_id,
                Meeting.case_id == case_id,
                Meeting.provider_event_id.in_(event_ids),
            )
        )
        existing_ids = set(existing_result.scalars().all())
        self.db.add_all(
            [meeting for meeting in meetings if meeting.provider_event_id not in existing_ids]
        )
        await self.db.commit()


class BriefingReportRepository(BaseRepository[BriefingReport]):
    def __init__(self, db: AsyncSession):
        super().__init__(BriefingReport, db)

    async def latest_by_case(self, org_id: str, case_id: str) -> BriefingReport | None:
        res = await self.db.execute(
            select(BriefingReport)
            .where(BriefingReport.org_id == org_id, BriefingReport.case_id == case_id)
            .order_by(BriefingReport.version.desc())
            .limit(1)
        )
        return res.scalar_one_or_none()

    async def next_version(self, org_id: str, case_id: str) -> int:
        latest = await self.latest_by_case(org_id, case_id)
        return (latest.version + 1) if latest else 1


class DeliveryAttemptRepository(BaseRepository[DeliveryAttempt]):
    def __init__(self, db: AsyncSession):
        super().__init__(DeliveryAttempt, db)

    async def get_by_idempotency_key(
        self, org_id: str, idempotency_key: str
    ) -> DeliveryAttempt | None:
        res = await self.db.execute(
            select(DeliveryAttempt).where(
                DeliveryAttempt.org_id == org_id,
                DeliveryAttempt.idempotency_key == idempotency_key,
            )
        )
        return res.scalar_one_or_none()

    async def touch(self, attempt: DeliveryAttempt, **fields) -> DeliveryAttempt:
        for k, v in fields.items():
            if hasattr(attempt, k):
                setattr(attempt, k, v)
        attempt.updated_at = utc_now()
        await self.db.commit()
        await self.db.refresh(attempt)
        return attempt


class CiScheduleRepository(BaseRepository[CiSchedule]):
    def __init__(self, db: AsyncSession):
        super().__init__(CiSchedule, db)

    async def list_enabled(self, org_id: str) -> list[CiSchedule]:
        res = await self.db.execute(
            select(CiSchedule).where(CiSchedule.org_id == org_id, CiSchedule.enabled.is_(True))
        )
        return list(res.scalars().all())

    async def list_due(self, now: datetime, limit: int = 50) -> list[CiSchedule]:
        res = await self.db.execute(
            select(CiSchedule)
            .where(
                CiSchedule.enabled.is_(True),
                CiSchedule.next_run_at.is_not(None),
                CiSchedule.next_run_at <= now,
            )
            .order_by(CiSchedule.next_run_at)
            .limit(limit)
        )
        return list(res.scalars().all())
