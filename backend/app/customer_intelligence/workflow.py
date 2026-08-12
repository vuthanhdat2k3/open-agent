from __future__ import annotations

import asyncio
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.observability.audit import log_action
from app.core.observability.genai import workflow_node_span
from app.customer_intelligence.contracts import (
    CompanyRecord,
    MeetingMatch,
    ReportSections,
    SearchHit,
)
from app.customer_intelligence.matching import match_companies, match_meetings
from app.customer_intelligence.oauth import load_fresh_credentials
from app.customer_intelligence.providers.research import (
    bind_calendar_provider,
    get_calendar_provider,
    get_company_provider,
    get_web_provider,
)
from app.customer_intelligence.renderer import render_markdown
from app.customer_intelligence.security import assert_safe_url
from app.db.base import utc_now
from app.models.customer_intelligence import (
    BriefingReport,
    CalendarConnection,
    InboundEmail,
    Meeting,
    ResearchCase,
    ResearchSource,
)
from app.repositories.customer_intelligence import (
    BriefingReportRepository,
    CalendarConnectionRepository,
    InboundEmailRepository,
    MeetingRepository,
    ResearchCaseRepository,
    ResearchSourceRepository,
)


class ResearchError(Exception):
    pass


async def _research_branch(
    case: ResearchCase,
    company: CompanyRecord,
    *,
    org_id: str,
) -> tuple[list[ResearchSource], list[str]]:
    """Run the web+news branches for one company, in parallel, bounded by timeout.

    Returns (sources, warnings). Never fabricates: failed/empty searches
    produce a warning, not invented data. URLs are SSRF-checked before they
    are persisted.
    """
    settings = get_settings()
    web = get_web_provider()
    warnings: list[str] = []

    async def _web_branch() -> list[SearchHit]:
        try:
            return await asyncio.wait_for(
                web.web_search(company.canonical_name, limit=5),
                timeout=settings.ci_research_timeout_s,
            )
        except TimeoutError:
            warnings.append(f"web search timed out for {company.canonical_name}")
            return []
        except Exception:  # noqa: BLE001 - partial research must remain reportable.
            warnings.append(f"web search failed for {company.canonical_name}")
            return []

    async def _news_branch() -> list[SearchHit]:
        try:
            return await asyncio.wait_for(
                web.news_search(company.canonical_name, limit=5, lookback_days=settings.ci_news_window_days),
                timeout=settings.ci_research_timeout_s,
            )
        except TimeoutError:
            warnings.append(f"news search timed out for {company.canonical_name}")
            return []
        except Exception:  # noqa: BLE001 - partial research must remain reportable.
            warnings.append(f"news search failed for {company.canonical_name}")
            return []

    web_hits, news_hits = await asyncio.gather(_web_branch(), _news_branch())
    if not web_hits:
        warnings.append(f"web research unavailable for {company.canonical_name}")
    if not news_hits:
        warnings.append(f"recent news unavailable for {company.canonical_name}")

    sources: list[ResearchSource] = []
    for hit, source_type in [(h, "website") for h in web_hits] + [(h, "news") for h in news_hits]:
        if assert_safe_url(hit.url):
            warnings.append(f"skipped unsafe url {hit.url[:120]}")
            continue
        sources.append(
            ResearchSource(
                org_id=org_id,
                case_id=case.id,
                url=hit.url,
                source_type=source_type,
                title=hit.title,
                publisher=hit.publisher,
                published_date=hit.published_date,
                retrieved_date=hit.retrieved_date,
                excerpt=hit.excerpt,
                domain=hit.domain,
                confidence=1.0,
            )
        )
    return sources, warnings


async def run_research(
    db: AsyncSession,
    *,
    org_id: str,
    case_id: str,
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    """Run the full research DAG for an INGESTED case.

    Steps: load case+email -> match companies -> parallel web/news/company
    branches -> calendar matching -> persist sources/meetings -> render and
    persist the 7-section report (versioned) -> transition to REPORT_READY.

    Returns a summary dict. Raises ResearchError on hard failures; soft
    failures (empty search, timeout) become warnings — never fabricated data.
    """
    settings = get_settings()
    case_repo = ResearchCaseRepository(db)
    email_repo = InboundEmailRepository(db)
    calendar_repo = CalendarConnectionRepository(db)
    source_repo = ResearchSourceRepository(db)
    meeting_repo = MeetingRepository(db)
    report_repo = BriefingReportRepository(db)

    case = await case_repo.get(org_id, case_id)
    if case is None:
        raise ResearchError("case not found")
    if case.status not in {"INGESTED", "RETRYING", "RESEARCHING"}:
        raise ResearchError(f"case is not researchable (status={case.status})")

    email = await email_repo.get(org_id, case.email_id)
    if email is None:
        raise ResearchError("case email not found")

    case.workflow_run_id = case.workflow_run_id or f"ci-{case.id}"
    case.started_at = utc_now()
    if case.status != "RESEARCHING":
        await case_repo.transition(case, "RESEARCHING")

    warnings: list[str] = []
    sources: list[ResearchSource] = []
    companies: list[CompanyRecord] = []
    meetings: list[MeetingMatch] = []

    with workflow_node_span(
        org_id=org_id,
        workflow_run_id=case.workflow_run_id,
        node_id="match",
        node_type="input",
        workflow_name="customer-intelligence",
    ):
        try:
            companies = await match_companies(email, get_company_provider())
        except Exception:  # noqa: BLE001 - company branch is optional.
            companies = []
            warnings.append("company lookup failed")
        if not companies and "company lookup failed" not in warnings:
            warnings.append("no company matched for this email")

        calendar_conn: CalendarConnection | None = await calendar_repo.get_connected(org_id)
        if calendar_conn is not None and calendar_conn.credentials_enc:
            case.calendar_connection_id = calendar_conn.id
            creds = await load_fresh_credentials(db, calendar_conn)
            cal = bind_calendar_provider(get_calendar_provider(), creds)
            try:
                events = await asyncio.wait_for(
                    cal.list_events(
                        from_=datetime.now(timezone.utc),
                        to=datetime.now(timezone.utc) + timedelta(days=30),
                        max_results=25,
                    ),
                    timeout=settings.ci_research_timeout_s,
                )
                meetings = match_meetings(events, companies)
            except TimeoutError:
                warnings.append("calendar lookup timed out")
            except Exception as e:  # noqa: BLE001
                warnings.append(f"calendar lookup failed: {type(e).__name__}")
        else:
            warnings.append("no calendar credentials, meeting matching skipped")

    with workflow_node_span(
        org_id=org_id,
        workflow_run_id=case.workflow_run_id,
        node_id="research",
        node_type="tool",
        workflow_name="customer-intelligence",
    ):
        for company in companies:
            branch_sources, branch_warnings = await _research_branch(case, company, org_id=org_id)
            sources.extend(branch_sources)
            warnings.extend(branch_warnings)

    unique_sources: list[ResearchSource] = []
    seen_urls: set[str] = set()
    for source in sources:
        normalized_url = source.url.rstrip("/")
        if normalized_url in seen_urls:
            continue
        seen_urls.add(normalized_url)
        source.url = normalized_url
        source.content_hash = hashlib.sha256(
            f"{source.url}|{source.title}|{source.excerpt}".encode()
        ).hexdigest()
        unique_sources.append(source)
    sources = unique_sources[: settings.ci_max_sources_per_case]
    if sources:
        await source_repo.bulk_create(sources)
    meeting_rows: list[Meeting] = []
    for m in meetings:
        meeting_rows.append(
            Meeting(
                org_id=org_id,
                case_id=case_id,
                provider_event_id=m.event.provider_event_id,
                title=m.event.title,
                start_at=m.event.start_at,
                end_at=m.event.end_at,
                attendees=m.event.attendees,
                organizer=m.event.organizer,
                description=m.event.description,
                location=m.event.location,
                match_type=m.match_type,
                confidence=m.confidence,
                matched_on=m.matched_on,
            )
        )
    if meeting_rows:
        await meeting_repo.bulk_upsert(meeting_rows)

    report_sections: ReportSections = {
        "executive_summary": _executive_summary(email, companies, meetings, warnings),
        "company_overview": [
            {
                "company_id": c.company_id,
                "canonical_name": c.canonical_name,
                "aliases": c.aliases,
                "industry": c.industry,
                "products": c.products,
                "domain": c.domain,
            }
            for c in companies
        ],
        "recent_news": [
            {
                "url": s.url,
                "title": s.title,
                "publisher": s.publisher,
                "published_date": s.published_date,
                "excerpt": s.excerpt,
                "domain": s.domain,
            }
            for s in sources
            if s.source_type == "news"
        ],
        "contact_information": [
            contact
            for c in companies
            for contact in c.contacts
        ],
        "upcoming_meetings": [
            {
                "provider_event_id": m.event.provider_event_id,
                "title": m.event.title,
                "start_at": m.event.start_at.isoformat(),
                "attendees": m.event.attendees,
                "match_type": m.match_type,
                "confidence": m.confidence,
            }
            for m in meetings
        ],
        "open_questions": _open_questions(warnings),
        "sources": [
            {
                "url": s.url,
                "title": s.title,
                "source_type": s.source_type,
                "publisher": s.publisher,
                "published_date": s.published_date,
                "retrieved_date": s.retrieved_date,
                "excerpt": s.excerpt,
                "domain": s.domain,
                "confidence": s.confidence,
            }
            for s in sources
        ],
    }
    version = await report_repo.next_version(org_id, case_id)
    report = BriefingReport(
        org_id=org_id,
        case_id=case_id,
        version=version,
        canonical_markdown=render_markdown(report_sections),
        rendering=None,
        confidence=min(len(sources) / max(len(companies), 1) / 5, 1.0) if companies else 0.0,
        status="ready",
    )
    await report_repo.create(report)

    case.company_name = companies[0].canonical_name if companies else None
    case.company_domain = companies[0].domain if companies else None
    case.confidence = report.confidence
    case.finished_at = utc_now()
    await case_repo.transition(case, "REPORT_READY")

    await log_action(
        db,
        org_id=org_id,
        actor_user_id=actor_user_id,
        action="ci.case.researched",
        resource_type="ci_case",
        resource_id=case_id,
        metadata={
            "companies": len(companies),
            "sources": len(sources),
            "meetings": len(meetings),
            "report_version": version,
            "warnings": len(warnings),
        },
    )
    return {
        "case_id": case_id,
        "companies": [c.canonical_name for c in companies],
        "sources": len(sources),
        "meetings": len(meetings),
        "report_version": version,
        "warnings": warnings,
    }


def _executive_summary(
    email: InboundEmail,
    companies: list[CompanyRecord],
    meetings: list[MeetingMatch],
    warnings: list[str],
) -> str:
    if not companies:
        return "No company could be matched to this email; research produced no company-level briefing."
    names = ", ".join(c.canonical_name for c in companies[:3])
    meeting_note = (
        f" {len(meetings)} upcoming meeting(s) matched." if meetings else " No upcoming meetings matched."
    )
    warning_note = f" {len(warnings)} research warning(s); see sources/open questions." if warnings else ""
    return (
        f"This briefing covers {names} based on the email "
        f"'{email.subject or '(no subject)'}' from {email.sender_email}."
        f"{meeting_note}{warning_note}"
    )


def _open_questions(warnings: list[str]) -> list[str]:
    if not warnings:
        return ["No open questions; all research branches completed."]
    return [f"Research branch incomplete: {w}" for w in warnings]
