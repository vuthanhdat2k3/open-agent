from __future__ import annotations

import hmac
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.base import gen_id, utc_now
from app.dependencies import (
    get_current_org_id,
    get_current_user,
    get_db,
    require_any_permission,
    require_permission,
)
from app.models.customer_intelligence import InboundEmail, ResearchCase
from app.models.user import User
from app.schemas.customer_intelligence import (
    ApprovalDecisionRequest,
    ApprovalOut,
    CalendarConnectionResponse,
    CaseDetail,
    CaseSummary,
    ConnectionCreate,
    ConnectionResponse,
    ConnectionSyncRequest,
    DeliverActionRequest,
    DriveConnectionResponse,
    ManualResearchRequest,
    MeetingResponse,
    ReportResponse,
    ScheduleCreate,
    ScheduleResponse,
    ScheduleUpdate,
    SourceResponse,
    SyncResult,
)
from app.services.customer_intelligence_service import CustomerIntelligenceService

router = APIRouter(prefix="/api/customer-intelligence", tags=["customer-intelligence"])
oauth_router = APIRouter(prefix="/api/customer-intelligence", tags=["customer-intelligence-oauth"])
webhook_router = APIRouter(prefix="/api/webhooks/google", tags=["webhooks"])


@webhook_router.post("/gmail", status_code=204)
async def gmail_push_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """Persist-only Gmail Pub/Sub hot path; workers perform all provider I/O."""
    if request.headers.get("content-length") and int(request.headers["content-length"]) > 1_000_000:
        raise HTTPException(413, "webhook payload too large")
    try:
        payload = await request.json()
    except ValueError as exc:
        raise HTTPException(400, "invalid webhook JSON") from exc
    from app.customer_intelligence.gmail_webhook import ingest_push

    await ingest_push(db, request, payload)


def _guard_enabled() -> None:
    if not get_settings().customer_intelligence_enabled:
        raise HTTPException(status_code=404, detail="customer intelligence is disabled")


def _ci_oauth_redirect_uri(kind: str, provider: str) -> str:
    """Build the browser-reachable callback, not the Docker service hostname."""
    base_url = get_settings().ci_backend_public_url.rstrip("/")
    return f"{base_url}/api/customer-intelligence/oauth/{kind}/{provider}/callback"


def _connection_owner(request: Request, current_user: User) -> str | None:
    """Admins see/manage the organization; users are limited to own OAuth data."""
    return None if getattr(request.state, "role", "user") == "admin" else current_user.id


async def _case_for_request(
    db: AsyncSession, *, org_id: str, case_id: str, request: Request, current_user: User
):
    from app.repositories.customer_intelligence import ResearchCaseRepository

    case = await ResearchCaseRepository(db).get(
        org_id,
        case_id,
        created_by_user_id=_connection_owner(request, current_user),
    )
    if case is None:
        raise HTTPException(status_code=404, detail="case not found")
    return case


@oauth_router.get("/oauth/{kind}/{provider}/start")
async def start_ci_oauth(
    kind: str,
    provider: str,
    request: Request,
    org_id: str = Depends(get_current_org_id),
    current_user: User = Depends(get_current_user),
    _permission: None = Depends(require_any_permission("ci:manage", "ci:personal:manage")),
):
    _guard_enabled()
    if kind not in {"email", "calendar", "drive"} or provider != "google":
        raise HTTPException(400, "unsupported Customer Intelligence OAuth connection")
    from app.customer_intelligence.oauth import authorization_url, create_oauth_state

    state = create_oauth_state(current_user.id, org_id, kind, provider)
    redirect_uri = _ci_oauth_redirect_uri(kind, provider)
    try:
        url = authorization_url(provider, kind, state, redirect_uri)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    response = JSONResponse({"url": url})
    response.set_cookie("ci_oauth_state", state, httponly=True, secure=get_settings().cookie_secure, samesite="lax", max_age=600)
    return response


@oauth_router.get("/oauth/{kind}/{provider}/callback", name="ci_oauth_callback")
async def ci_oauth_callback(kind: str, provider: str, request: Request, db: AsyncSession = Depends(get_db)):
    _guard_enabled()
    from app.customer_intelligence.oauth import account_email, exchange_code, verify_oauth_state
    from app.customer_intelligence.security import encrypt_credentials

    state = request.query_params.get("state", "")
    if not state or not hmac.compare_digest(state, request.cookies.get("ci_oauth_state", "")):
        raise HTTPException(400, "invalid OAuth state")
    try:
        payload = verify_oauth_state(state)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if payload.get("kind") != kind or payload.get("provider") != provider:
        raise HTTPException(400, "OAuth state does not match connection")
    code = request.query_params.get("code")
    if not code:
        raise HTTPException(400, request.query_params.get("error", "OAuth authorization failed"))
    redirect_uri = _ci_oauth_redirect_uri(kind, provider)
    try:
        token = await exchange_code(provider, code, redirect_uri, kind)
        email = await account_email(provider, token.get("access_token", ""))
    except Exception as exc:  # noqa: BLE001 - do not expose provider response details.
        raise HTTPException(400, "OAuth token exchange failed") from exc
    if not email:
        raise HTTPException(400, "OAuth provider did not return an account email")

    calendar_provider = "google"
    credentials = dict(token)
    if token.get("expires_in"):
        credentials["expires_at"] = time.time() + int(token["expires_in"])
    credentials.update({"oauth_provider": provider, "calendar_provider": calendar_provider if kind == "calendar" else None})
    if kind == "email":
        connection_provider = "gmail"
        existing = await CustomerIntelligenceService(db).connections.get_by_account(payload["org_id"], email)
        if existing is not None and existing.created_by_user_id not in {None, payload["user_id"]}:
            raise HTTPException(409, "This Google account is already connected by another user")
        await CustomerIntelligenceService(db).connect(
            org_id=payload["org_id"],
            provider=connection_provider,
            account_email=email,
            oauth_payload=credentials,
            created_by_user_id=payload["user_id"],
        )
    elif kind == "calendar":
        from app.models.customer_intelligence import CalendarConnection
        from app.repositories.customer_intelligence import CalendarConnectionRepository

        repo = CalendarConnectionRepository(db)
        connection = await repo.get_by_account(payload["org_id"], calendar_provider, email)
        if connection is not None and connection.created_by_user_id not in {None, payload["user_id"]}:
            raise HTTPException(409, "This Google account is already connected by another user")
        if connection is None:
            await repo.create(CalendarConnection(org_id=payload["org_id"], provider=calendar_provider, account_email=email, credentials_enc=encrypt_credentials(credentials), status="connected", created_by_user_id=payload["user_id"]))
        else:
            await repo.update(connection, {"credentials_enc": encrypt_credentials(credentials), "status": "connected", "error": None, "created_by_user_id": connection.created_by_user_id or payload["user_id"]})
    else:
        from app.models.customer_intelligence import DriveConnection
        from app.repositories.customer_intelligence import DriveConnectionRepository

        repo = DriveConnectionRepository(db)
        connection = await repo.get_by_account(payload["org_id"], email)
        if connection is not None and connection.created_by_user_id not in {None, payload["user_id"]}:
            raise HTTPException(409, "This Google account is already connected by another user")
        if connection is None:
            await repo.create(DriveConnection(org_id=payload["org_id"], provider="google", account_email=email, credentials_enc=encrypt_credentials(credentials), status="connected", created_by_user_id=payload["user_id"]))
        else:
            await repo.update(connection, {"credentials_enc": encrypt_credentials(credentials), "status": "connected", "error": None, "created_by_user_id": connection.created_by_user_id or payload["user_id"]})
    response = RedirectResponse(get_settings().ci_frontend_redirect_url)
    response.delete_cookie("ci_oauth_state")
    return response



async def _log_ci_action(
    db: AsyncSession,
    *,
    org_id: str,
    actor_user_id: str | None,
    action: str,
    resource_id: str | None = None,
    metadata: dict | None = None,
) -> None:
    """Append one append-only audit row for a customer-intelligence operation.

    Imported lazily to keep the FastAPI route module free of heavyweight side
    effects at import time.
    """
    from app.core.observability.audit import log_action

    await log_action(
        db,
        org_id=org_id,
        actor_user_id=actor_user_id,
        action=action,
        resource_type="ci_schedule",
        resource_id=resource_id,
        metadata=metadata or {},
    )


@router.get(
    "/connections",
    response_model=list[ConnectionResponse],
    dependencies=[Depends(require_permission("ci:read"))],
)
async def list_connections(
    org_id: str = Depends(get_current_org_id),
    current_user: User = Depends(get_current_user),
    request: Request = None,
    db: AsyncSession = Depends(get_db),
):
    _guard_enabled()
    return await CustomerIntelligenceService(db).status(org_id=org_id, created_by_user_id=_connection_owner(request, current_user))


@router.get("/drive-connections", response_model=list[DriveConnectionResponse], dependencies=[Depends(require_permission("ci:read"))])
async def list_drive_connections(
    org_id: str = Depends(get_current_org_id),
    current_user: User = Depends(get_current_user),
    request: Request = None,
    db: AsyncSession = Depends(get_db),
):
    _guard_enabled()
    from app.repositories.customer_intelligence import DriveConnectionRepository

    connections = await DriveConnectionRepository(db).list(org_id, created_by_user_id=_connection_owner(request, current_user))
    return [DriveConnectionResponse(id=item.id, provider=item.provider, account_email=item.account_email, status=item.status, error=item.error, has_credentials=bool(item.credentials_enc), created_at=item.created_at) for item in connections]


@router.delete("/drive-connections/{connection_id}", response_model=DriveConnectionResponse, dependencies=[Depends(require_permission("ci:read"))])
async def disconnect_drive_connection(
    connection_id: str,
    org_id: str = Depends(get_current_org_id),
    current_user: User = Depends(get_current_user),
    request: Request = None,
    db: AsyncSession = Depends(get_db),
):
    _guard_enabled()
    from app.customer_intelligence.oauth import revoke_provider_token
    from app.customer_intelligence.security import decrypt_credentials
    from app.repositories.customer_intelligence import DriveConnectionRepository

    repo = DriveConnectionRepository(db)
    connection = await repo.get(org_id, connection_id, created_by_user_id=_connection_owner(request, current_user))
    if connection is None:
        raise HTTPException(404, "Drive connection not found")
    if connection.credentials_enc:
        try:
            await revoke_provider_token("google", decrypt_credentials(connection.credentials_enc))
        except Exception:  # noqa: BLE001 - always clear local access.
            pass
    updated = await repo.update(connection, {"status": "disconnected", "credentials_enc": None})
    return DriveConnectionResponse(id=updated.id, provider=updated.provider, account_email=updated.account_email, status=updated.status, error=updated.error, has_credentials=False, created_at=updated.created_at)


@router.get(
    "/calendar-connections",
    response_model=list[CalendarConnectionResponse],
    dependencies=[Depends(require_permission("ci:read"))],
)
async def list_calendar_connections(
    org_id: str = Depends(get_current_org_id),
    current_user: User = Depends(get_current_user),
    request: Request = None,
    db: AsyncSession = Depends(get_db),
):
    _guard_enabled()
    from app.repositories.customer_intelligence import CalendarConnectionRepository

    connections = await CalendarConnectionRepository(db).list(org_id, created_by_user_id=_connection_owner(request, current_user))
    return [CalendarConnectionResponse(id=item.id, provider=item.provider, account_email=item.account_email, status=item.status, error=item.error, has_credentials=bool(item.credentials_enc), created_at=item.created_at) for item in connections]


@router.delete("/calendar-connections/{connection_id}", response_model=CalendarConnectionResponse, dependencies=[Depends(require_permission("ci:read"))])
async def disconnect_calendar_connection(
    connection_id: str,
    org_id: str = Depends(get_current_org_id),
    current_user: User = Depends(get_current_user),
    request: Request = None,
    db: AsyncSession = Depends(get_db),
):
    _guard_enabled()
    from app.repositories.customer_intelligence import CalendarConnectionRepository

    repo = CalendarConnectionRepository(db)
    connection = await repo.get(org_id, connection_id, created_by_user_id=_connection_owner(request, current_user))
    if connection is None:
        raise HTTPException(404, "calendar connection not found")
    if connection.credentials_enc:
        from app.customer_intelligence.oauth import revoke_provider_token
        from app.customer_intelligence.security import decrypt_credentials

        try:
            credentials = decrypt_credentials(connection.credentials_enc)
            await revoke_provider_token(credentials.get("oauth_provider", connection.provider), credentials)
        except Exception:  # noqa: BLE001 - local disconnect must still clear credentials.
            pass
    updated = await repo.update(connection, {"status": "disconnected", "credentials_enc": None})
    return CalendarConnectionResponse(id=updated.id, provider=updated.provider, account_email=updated.account_email, status=updated.status, error=updated.error, has_credentials=False, created_at=updated.created_at)


@router.post(
    "/connections",
    response_model=ConnectionResponse,
    status_code=201,
    dependencies=[Depends(require_permission("ci:manage"))],
)
async def create_connection(
    body: ConnectionCreate,
    org_id: str = Depends(get_current_org_id),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _guard_enabled()
    raise HTTPException(400, "use the OAuth connect flow for email connections")


@router.delete(
    "/connections/{connection_id}",
    response_model=ConnectionResponse,
    dependencies=[Depends(require_permission("ci:read"))],
)
async def disconnect_connection(
    connection_id: str,
    org_id: str = Depends(get_current_org_id),
    current_user: User = Depends(get_current_user),
    request: Request = None,
    db: AsyncSession = Depends(get_db),
):
    _guard_enabled()
    owner_id = _connection_owner(request, current_user)
    if owner_id is not None and await CustomerIntelligenceService(db).connections.get(org_id, connection_id, created_by_user_id=owner_id) is None:
        raise HTTPException(status_code=404, detail="connection not found")
    result = await CustomerIntelligenceService(db).disconnect(
        org_id=org_id, connection_id=connection_id, actor_user_id=current_user.id
    )
    if result is None:
        raise HTTPException(status_code=404, detail="connection not found")
    return result


@router.post(
    "/connections/{connection_id}/sync",
    response_model=SyncResult,
    dependencies=[Depends(require_any_permission("ci:manage", "ci:personal:manage"))],
)
async def sync_connection(
    connection_id: str,
    body: ConnectionSyncRequest,
    org_id: str = Depends(get_current_org_id),
    current_user: User = Depends(get_current_user),
    request: Request = None,
    db: AsyncSession = Depends(get_db),
):
    _guard_enabled()
    from app.customer_intelligence.ingest import sync_connection

    owner_id = _connection_owner(request, current_user)
    if await CustomerIntelligenceService(db).connections.get(
        org_id, connection_id, created_by_user_id=owner_id
    ) is None:
        raise HTTPException(status_code=404, detail="connection not found")

    return await sync_connection(
        db,
        org_id=org_id,
        connection_id=connection_id,
        trigger=body.trigger,
        max_messages=body.max_messages,
        actor_user_id=current_user.id,
    )


@router.get(
    "/schedules",
    response_model=list[ScheduleResponse],
    dependencies=[Depends(require_permission("ci:read"))],
)
async def list_schedules(
    org_id: str = Depends(get_current_org_id),
    current_user: User = Depends(get_current_user),
    request: Request = None,
    db: AsyncSession = Depends(get_db),
):
    _guard_enabled()
    from app.repositories.customer_intelligence import CiScheduleRepository

    schedules = await CiScheduleRepository(db).list(
        org_id,
        created_by_user_id=_connection_owner(request, current_user),
    )
    return [
        ScheduleResponse(
            id=s.id,
            connection_id=s.connection_id,
            enabled=s.enabled,
            run_time=s.run_time,
            timezone=s.timezone,
            last_run_at=s.last_run_at,
            next_run_at=s.next_run_at,
        )
        for s in schedules
    ]


@router.post(
    "/schedules",
    response_model=ScheduleResponse,
    status_code=201,
    dependencies=[Depends(require_any_permission("ci:manage", "ci:personal:manage"))],
)
async def create_schedule(
    body: ScheduleCreate,
    org_id: str = Depends(get_current_org_id),
    current_user: User = Depends(get_current_user),
    request: Request = None,
    db: AsyncSession = Depends(get_db),
):
    _guard_enabled()
    from app.customer_intelligence.scheduler import compute_next_run_at
    from app.models.customer_intelligence import CiSchedule
    from app.repositories.customer_intelligence import (
        CiScheduleRepository,
        EmailConnectionRepository,
    )

    conn = await EmailConnectionRepository(db).get(
        org_id,
        body.connection_id,
        created_by_user_id=_connection_owner(request, current_user),
    )
    if conn is None:
        raise HTTPException(status_code=404, detail="connection not found")

    schedule = CiSchedule(
        org_id=org_id,
        connection_id=body.connection_id,
        enabled=body.enabled,
        run_time=body.run_time,
        timezone=body.timezone,
        next_run_at=compute_next_run_at(body.run_time, body.timezone),
        created_by_user_id=current_user.id,
    )
    created = await CiScheduleRepository(db).create(schedule)
    await _log_ci_action(
        db,
        org_id=org_id,
        actor_user_id=current_user.id,
        action="ci.schedule.created",
        resource_id=created.id,
        metadata={
            "connection_id": created.connection_id,
            "run_time": created.run_time,
            "timezone": created.timezone,
            "enabled": created.enabled,
        },
    )
    return ScheduleResponse(
        id=created.id,
        connection_id=created.connection_id,
        enabled=created.enabled,
        run_time=created.run_time,
        timezone=created.timezone,
        last_run_at=created.last_run_at,
        next_run_at=created.next_run_at,
    )


@router.patch(
    "/schedules/{schedule_id}",
    response_model=ScheduleResponse,
    dependencies=[Depends(require_any_permission("ci:manage", "ci:personal:manage"))],
)
async def update_schedule(
    schedule_id: str,
    body: ScheduleUpdate,
    org_id: str = Depends(get_current_org_id),
    current_user: User = Depends(get_current_user),
    request: Request = None,
    db: AsyncSession = Depends(get_db),
):
    _guard_enabled()
    from app.customer_intelligence.scheduler import compute_next_run_at
    from app.repositories.customer_intelligence import CiScheduleRepository

    schedule = await CiScheduleRepository(db).get(
        org_id,
        schedule_id,
        created_by_user_id=_connection_owner(request, current_user),
    )
    if schedule is None:
        raise HTTPException(status_code=404, detail="schedule not found")

    data = body.model_dump(exclude_unset=True)
    if "run_time" in data or "timezone" in data:
        data["next_run_at"] = compute_next_run_at(
            data.get("run_time", schedule.run_time),
            data.get("timezone", schedule.timezone),
        )
    updated = await CiScheduleRepository(db).update(schedule, data)
    await _log_ci_action(
        db,
        org_id=org_id,
        actor_user_id=current_user.id,
        action="ci.schedule.updated",
        resource_id=updated.id,
        metadata={
            "connection_id": updated.connection_id,
            "run_time": updated.run_time,
            "timezone": updated.timezone,
            "enabled": updated.enabled,
        },
    )
    return ScheduleResponse(
        id=updated.id,
        connection_id=updated.connection_id,
        enabled=updated.enabled,
        run_time=updated.run_time,
        timezone=updated.timezone,
        last_run_at=updated.last_run_at,
        next_run_at=updated.next_run_at,
    )


@router.delete(
    "/schedules/{schedule_id}",
    status_code=204,
    dependencies=[Depends(require_any_permission("ci:manage", "ci:personal:manage"))],
)
async def delete_schedule(
    schedule_id: str,
    org_id: str = Depends(get_current_org_id),
    current_user: User = Depends(get_current_user),
    request: Request = None,
    db: AsyncSession = Depends(get_db),
):
    _guard_enabled()
    from app.repositories.customer_intelligence import CiScheduleRepository

    schedule = await CiScheduleRepository(db).get(
        org_id,
        schedule_id,
        created_by_user_id=_connection_owner(request, current_user),
    )
    if schedule is None:
        raise HTTPException(status_code=404, detail="schedule not found")
    deleted = await CiScheduleRepository(db).delete(org_id, schedule_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="schedule not found")
    await _log_ci_action(
        db,
        org_id=org_id,
        actor_user_id=current_user.id,
        action="ci.schedule.deleted",
        resource_id=schedule_id,
    )


@router.post(
    "/schedules/{schedule_id}/run",
    response_model=SyncResult,
    dependencies=[Depends(require_any_permission("ci:manage", "ci:personal:manage"))],
)
async def run_schedule(
    schedule_id: str,
    org_id: str = Depends(get_current_org_id),
    current_user: User = Depends(get_current_user),
    request: Request = None,
    db: AsyncSession = Depends(get_db),
):
    _guard_enabled()
    from app.customer_intelligence.ingest import IngestionError
    from app.customer_intelligence.scheduler import run_schedule_now
    from app.repositories.customer_intelligence import CiScheduleRepository

    try:
        if await CiScheduleRepository(db).get(
            org_id,
            schedule_id,
            created_by_user_id=_connection_owner(request, current_user),
        ) is None:
            raise KeyError("schedule not found")
        result = await run_schedule_now(
            db, org_id=org_id, schedule_id=schedule_id, actor_user_id=current_user.id
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="schedule not found")
    except IngestionError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return SyncResult(
        connection_id=result["connection_id"],
        synced=result["synced"],
        deduplicated=0,
        new_cases=result["new_cases"],
        correlation_id=result.get("correlation_id"),
    )


@router.get(
    "/cases",
    response_model=list[CaseSummary],
    dependencies=[Depends(require_permission("ci:read"))],
)
async def list_cases(
    org_id: str = Depends(get_current_org_id),
    current_user: User = Depends(get_current_user),
    request: Request = None,
    db: AsyncSession = Depends(get_db),
):
    _guard_enabled()
    from app.repositories.customer_intelligence import ResearchCaseRepository

    cases = await ResearchCaseRepository(db).list_by_status(
        org_id,
        limit=100,
        created_by_user_id=_connection_owner(request, current_user),
    )
    return [
        CaseSummary(
            id=c.id,
            email_id=c.email_id,
            company_name=c.company_name,
            company_domain=c.company_domain,
            status=c.status,
            confidence=c.confidence,
            trigger=c.trigger,
            created_at=c.created_at,
            finished_at=c.finished_at,
        )
        for c in cases
    ]


@router.post(
    "/cases/manual",
    response_model=CaseSummary,
    status_code=201,
    dependencies=[Depends(require_any_permission("ci:manage", "ci:personal:manage"))],
)
async def create_manual_case(
    body: ManualResearchRequest,
    org_id: str = Depends(get_current_org_id),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a private research request without requiring a Gmail connection."""
    _guard_enabled()
    from app.core.workflow.queue import enqueue_ci_research

    domain = (body.company_domain or "").strip().lower() or "manual-research.local"
    sender_email = f"research@{domain}"
    email = InboundEmail(
        org_id=org_id,
        connection_id=None,
        provider="manual",
        provider_message_id=f"manual-{gen_id()}",
        sender_name=body.company_name,
        sender_email=sender_email,
        sender_domain=domain,
        recipients=[current_user.email],
        subject=f"Manual research: {body.company_name}",
        body_text="\n".join(
            part for part in [
                f"Company: {body.company_name}",
                f"Domain: {domain}" if body.company_domain else None,
                f"Research question: {body.question}" if body.question else None,
            ] if part
        ),
        received_at=utc_now(),
        content_hash=gen_id(),
        created_by_user_id=current_user.id,
    )
    db.add(email)
    await db.flush()
    case = ResearchCase(
        org_id=org_id,
        email_id=email.id,
        connection_id=None,
        trigger="manual",
        status="INGESTED",
        created_by_user_id=current_user.id,
    )
    db.add(case)
    await db.commit()
    await db.refresh(case)
    try:
        await enqueue_ci_research(org_id, case.id)
    except Exception:  # noqa: BLE001 - dispatcher cron will recover the case.
        pass
    return CaseSummary(
        id=case.id,
        email_id=case.email_id,
        company_name=body.company_name,
        company_domain=body.company_domain,
        status=case.status,
        confidence=case.confidence,
        trigger=case.trigger,
        created_at=case.created_at,
        finished_at=case.finished_at,
    )


@router.get(
    "/cases/{case_id}",
    response_model=CaseDetail,
    dependencies=[Depends(require_permission("ci:read"))],
)
async def get_case(
    case_id: str,
    org_id: str = Depends(get_current_org_id),
    current_user: User = Depends(get_current_user),
    request: Request = None,
    db: AsyncSession = Depends(get_db),
):
    _guard_enabled()
    from app.repositories.customer_intelligence import (
        BriefingReportRepository,
        MeetingRepository,
        ResearchSourceRepository,
    )

    case = await _case_for_request(
        db,
        org_id=org_id,
        case_id=case_id,
        request=request,
        current_user=current_user,
    )
    sources = await ResearchSourceRepository(db).list_by_case(org_id, case_id)
    meetings = await MeetingRepository(db).list_by_case(org_id, case_id)
    report = await BriefingReportRepository(db).latest_by_case(org_id, case_id)
    return CaseDetail(
        id=case.id,
        email_id=case.email_id,
        company_name=case.company_name,
        company_domain=case.company_domain,
        status=case.status,
        confidence=case.confidence,
        trigger=case.trigger,
        created_at=case.created_at,
        finished_at=case.finished_at,
        error=case.error,
        sources=[
            SourceResponse(
                id=s.id,
                url=s.url,
                source_type=s.source_type,
                title=s.title,
                publisher=s.publisher,
                published_date=s.published_date,
                retrieved_date=s.retrieved_date,
                excerpt=s.excerpt,
                confidence=s.confidence,
            )
            for s in sources
        ],
        meetings=[
            MeetingResponse(
                id=m.id,
                provider_event_id=m.provider_event_id,
                title=m.title,
                start_at=m.start_at,
                end_at=m.end_at,
                attendees=m.attendees,
                match_type=m.match_type,
                confidence=m.confidence,
            )
            for m in meetings
        ],
        report=(
            ReportResponse(
                id=report.id,
                case_id=report.case_id,
                version=report.version,
                canonical_markdown=report.canonical_markdown,
                rendering=report.rendering,
                confidence=report.confidence,
                status=report.status,
                created_at=report.created_at,
            )
            if report
            else None
        ),
    )


class _ResearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


@router.post(
    "/cases/{case_id}/research",
    response_model=SyncResult,
    dependencies=[Depends(require_any_permission("ci:manage", "ci:personal:manage"))],
)
async def research_case(
    case_id: str,
    body: _ResearchRequest | None = None,
    org_id: str = Depends(get_current_org_id),
    current_user: User = Depends(get_current_user),
    request: Request = None,
    db: AsyncSession = Depends(get_db),
):
    _guard_enabled()
    from app.customer_intelligence.workflow import ResearchError

    try:
        await _case_for_request(
            db,
            org_id=org_id,
            case_id=case_id,
            request=request,
            current_user=current_user,
        )
        result = await CustomerIntelligenceService(db).research_case(
            org_id=org_id, case_id=case_id, actor_user_id=current_user.id
        )
    except ResearchError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return SyncResult(
        connection_id=case_id,
        synced=int(result["sources"]),
        deduplicated=int(result["meetings"]),
        new_cases=1,
        warnings=result["warnings"],
    )


@router.post(
    "/cases/{case_id}/retry",
    response_model=CaseSummary,
    dependencies=[Depends(require_any_permission("ci:manage", "ci:personal:manage"))],
)
async def retry_case(
    case_id: str,
    org_id: str = Depends(get_current_org_id),
    current_user: User = Depends(get_current_user),
    request: Request = None,
    db: AsyncSession = Depends(get_db),
):
    _guard_enabled()
    try:
        await _case_for_request(
            db,
            org_id=org_id,
            case_id=case_id,
            request=request,
            current_user=current_user,
        )
        case = await CustomerIntelligenceService(db).retry_case(
            org_id=org_id,
            case_id=case_id,
            actor_user_id=current_user.id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return CaseSummary(
        id=case.id,
        email_id=case.email_id,
        company_name=case.company_name,
        company_domain=case.company_domain,
        status=case.status,
        confidence=case.confidence,
        trigger=case.trigger,
        created_at=case.created_at,
        finished_at=case.finished_at,
    )


def _deliver_payload(body: DeliverActionRequest) -> dict:
    if body.action != "send_email":
        return {"action": body.action}
    return {
        "action": body.action,
        "to": body.to or "",
        "subject": body.subject or "",
        "body": body.body or "",
    }


@router.get(
    "/cases/{case_id}/approval",
    response_model=ApprovalOut | None,
    dependencies=[Depends(require_permission("ci:read"))],
)
async def get_case_approval(
    case_id: str,
    org_id: str = Depends(get_current_org_id),
    current_user: User = Depends(get_current_user),
    request: Request = None,
    db: AsyncSession = Depends(get_db),
):
    _guard_enabled()
    await _case_for_request(
        db,
        org_id=org_id,
        case_id=case_id,
        request=request,
        current_user=current_user,
    )
    approval = await CustomerIntelligenceService(db).get_case_approval(
        org_id=org_id, case_id=case_id
    )
    if approval is None:
        raise HTTPException(status_code=404, detail="no approval for case")
    return approval


@router.post(
    "/cases/{case_id}/deliver",
    response_model=ApprovalOut,
    dependencies=[Depends(require_any_permission("ci:manage", "ci:personal:manage"))],
)
async def propose_delivery(
    case_id: str,
    body: DeliverActionRequest,
    org_id: str = Depends(get_current_org_id),
    current_user: User = Depends(get_current_user),
    request: Request = None,
    db: AsyncSession = Depends(get_db),
):
    _guard_enabled()
    try:
        await _case_for_request(
            db,
            org_id=org_id,
            case_id=case_id,
            request=request,
            current_user=current_user,
        )
        return await CustomerIntelligenceService(db).propose_delivery(
            org_id=org_id,
            case_id=case_id,
            action=body.action,
            payload=_deliver_payload(body),
            requested_by=current_user.id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post(
    "/cases/{case_id}/approval/{approval_id}/decide",
    response_model=ApprovalOut,
    dependencies=[Depends(require_any_permission("ci:manage", "ci:personal:manage"))],
)
async def decide_case_delivery(
    case_id: str,
    approval_id: str,
    body: ApprovalDecisionRequest,
    org_id: str = Depends(get_current_org_id),
    current_user: User = Depends(get_current_user),
    request: Request = None,
    db: AsyncSession = Depends(get_db),
):
    _guard_enabled()
    try:
        await _case_for_request(
            db,
            org_id=org_id,
            case_id=case_id,
            request=request,
            current_user=current_user,
        )
        return await CustomerIntelligenceService(db).decide_delivery(
            org_id=org_id,
            approval_id=approval_id,
            case_id=case_id,
            decision=body.decision,
            decided_by=current_user.id,
            reason=body.reason,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
