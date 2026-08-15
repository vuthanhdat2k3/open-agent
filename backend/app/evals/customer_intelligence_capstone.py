"""Deterministic Customer Intelligence capstone evaluation harness.

The harness is intentionally offline: it uses the six-company fixture provider,
fixture inbound messages, deterministic web/news/calendar providers, and the
existing evaluation case/grader contracts. It is suitable for CI and never
calls an LLM, production database, email provider, or live search engine.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any

from app.customer_intelligence.contracts import (
    CalendarEvent,
    CompanyRecord,
    NormalizedEmail,
    ReportSections,
    SearchHit,
)
from app.customer_intelligence.providers.fixture_company import FixtureCompanyProvider
from app.customer_intelligence.renderer import render_markdown
from app.db.base import gen_id
from app.evals.customer_intelligence_fixture import FIXTURE_COMPANIES
from app.evals.grader import Grade, grade_output
from app.models.evaluation import EvaluationCase, EvaluationSuite

CAPSTONE_SUITE_NAME = "customer-intelligence-capstone"
CAPSTONE_SOURCE_COUNT = 12
CAPSTONE_MAX_LATENCY_MS = 42_000
CAPSTONE_REQUIRED_SECTIONS = (
    "executive_summary",
    "company_overview",
    "recent_news",
    "contact_information",
    "upcoming_meetings",
    "open_questions",
    "sources",
)


@dataclass(frozen=True)
class FixtureMeeting:
    title: str
    attendee: str
    match_type: str


FIXTURE_MEETINGS: dict[str, FixtureMeeting] = {
    "fpt software": FixtureMeeting("FPT Software discovery call", "partner@fptsoftware.com", "confirmed_match"),
    "vinamilk": FixtureMeeting("Vinamilk partnership review", "procurement@vinamilk.com.vn", "confirmed_match"),
    "samsung vietnam": FixtureMeeting("Samsung Vietnam account planning", "team@samsung.com", "confirmed_match"),
    "shopee vietnam": FixtureMeeting("Shopee Vietnam integration briefing", "merchant@shopee.vn", "confirmed_match"),
    "viettel solutions": FixtureMeeting("Viettel Solutions platform review", "solutions@viettel.com.vn", "confirmed_match"),
    "bosch": FixtureMeeting("Bosch technology partnership", "engineering@bosch.com", "confirmed_match"),
}


@dataclass(frozen=True)
class CapstoneCaseRun:
    case: EvaluationCase
    email: NormalizedEmail
    sections: ReportSections
    output: str
    observed_tools: list[str]
    latency_ms: int


@dataclass(frozen=True)
class CapstoneEvaluationReport:
    suite_name: str
    total_cases: int
    passed_cases: int
    completeness: float
    minimum_source_count: int
    freshness_passed: bool
    p95_latency_ms: int
    grades: dict[str, Grade]

    @property
    def passed(self) -> bool:
        return (
            self.passed_cases == self.total_cases
            and self.completeness >= 0.98
            and self.minimum_source_count >= CAPSTONE_SOURCE_COUNT
            and self.freshness_passed
            and self.p95_latency_ms <= CAPSTONE_MAX_LATENCY_MS
        )


class FixtureInboundEmailProvider:
    """Six deterministic inbound email fixtures, one for each company."""

    def __init__(self, *, now: datetime | None = None) -> None:
        self.now = now or datetime.now(timezone.utc)

    def list_messages(self) -> list[NormalizedEmail]:
        messages: list[NormalizedEmail] = []
        for index, record in enumerate(FIXTURE_COMPANIES.values(), start=1):
            messages.append(
                NormalizedEmail(
                    provider="fixture",
                    provider_message_id=f"fixture-message-{index}",
                    thread_id=f"fixture-thread-{index}",
                    sender_name=f"{record.canonical_name} Partnerships",
                    sender_email=f"partnerships@{record.domain or 'fixture.example'}",
                    sender_domain=record.domain or "fixture.example",
                    recipients=["owner@example.test"],
                    subject=f"Meeting preparation: {record.canonical_name}",
                    body_text=f"Please prepare a briefing for our upcoming {record.canonical_name} meeting.",
                    body_html=None,
                    attachments=[],
                    received_at=self.now.replace(tzinfo=None),
                )
            )
        return messages


class FixtureWebResearchProvider:
    """Deterministic web/news provider; unknown companies return no hits."""

    def __init__(self, *, now: datetime | None = None) -> None:
        self.now = now or datetime.now(timezone.utc)

    def _record(self, query: str) -> CompanyRecord | None:
        normalized = query.casefold()
        for record in FIXTURE_COMPANIES.values():
            if normalized in record.canonical_name.casefold() or any(normalized in alias.casefold() for alias in record.aliases):
                return record
        return None

    def _hits(self, record: CompanyRecord, source_type: str, limit: int) -> list[SearchHit]:
        hits: list[SearchHit] = []
        base = record.domain or "fixture.example"
        for index in range(6):
            published = (self.now.date() - timedelta(days=index + (1 if source_type == "news" else 8))).isoformat()
            hits.append(
                SearchHit(
                    url=f"https://{base}/fixture/{source_type}/{index + 1}",
                    title=f"{record.canonical_name} {source_type.title()} Brief {index + 1}",
                    publisher=record.canonical_name,
                    published_date=published,
                    retrieved_date=self.now.date().isoformat(),
                    excerpt=f"Deterministic {source_type} evidence for {record.canonical_name}: fixture item {index + 1}.",
                    domain=base,
                )
            )
        return hits[:limit]

    async def web_search(self, query: str, limit: int = 5) -> list[SearchHit]:
        record = self._record(query)
        return self._hits(record, "website", limit) if record else []

    async def news_search(self, query: str, limit: int = 5, lookback_days: int = 30) -> list[SearchHit]:
        del lookback_days
        record = self._record(query)
        return self._hits(record, "news", limit) if record else []


class FixtureCalendarProvider:
    def __init__(self, *, now: datetime | None = None) -> None:
        self.now = now or datetime.now(timezone.utc)

    def event_for(self, record: CompanyRecord) -> CalendarEvent:
        meeting = FIXTURE_MEETINGS[next(key for key, value in FIXTURE_COMPANIES.items() if value.company_id == record.company_id)]
        start = self.now + timedelta(days=2)
        return CalendarEvent(
            provider_event_id=f"fixture-event-{record.company_id}",
            title=meeting.title,
            start_at=start,
            end_at=start + timedelta(hours=1),
            attendees=[meeting.attendee, "owner@example.test"],
            organizer="owner@example.test",
            description=f"Fixture calendar event for {record.canonical_name}",
            location="Video call",
        )


def build_customer_intelligence_capstone_suite(
    org_id: str = "fixture-org",
    agent_id: str = "fixture-agent",
    user_id: str | None = None,
) -> tuple[EvaluationSuite, list[EvaluationCase]]:
    """Build the persisted evaluation model objects without touching a DB."""
    suite = EvaluationSuite(
        id=gen_id(),
        org_id=org_id,
        agent_id=agent_id,
        name=CAPSTONE_SUITE_NAME,
        description="Deterministic six-company Customer Intelligence capstone evaluation",
        dataset_version=1,
        created_by_user_id=user_id,
    )
    cases: list[EvaluationCase] = []
    for ordinal, (key, record) in enumerate(FIXTURE_COMPANIES.items(), start=1):
        email = FixtureInboundEmailProvider().list_messages()[ordinal - 1]
        cases.append(
            EvaluationCase(
                id=gen_id(),
                org_id=org_id,
                suite_id=suite.id,
                input=json.dumps({"email": email.body_text, "company": record.canonical_name}),
                expected_output=None,
                required_substrings=[record.canonical_name, "Executive Summary", "Sources"],
                expected_tools=["email_list_new", "company_search", "web_search", "news_search", "calendar_list_events"],
                forbidden_patterns=["api_key", "access_token", "refresh_token"],
                max_latency_ms=CAPSTONE_MAX_LATENCY_MS,
                metadata_={
                    "company_key": key,
                    "company_name": record.canonical_name,
                    "expected_meeting_match": FIXTURE_MEETINGS[key].match_type,
                    "fixture": True,
                    "missing_provider": False,
                },
                ordinal=ordinal,
                added_in_version=1,
            )
        )
    return suite, cases


def _source_dict(hit: SearchHit) -> dict[str, Any]:
    return {
        "url": hit.url,
        "title": hit.title,
        "publisher": hit.publisher,
        "published_date": hit.published_date,
        "retrieved_date": hit.retrieved_date,
        "excerpt": hit.excerpt,
    }


async def run_fixture_case(case: EvaluationCase, *, now: datetime | None = None) -> CapstoneCaseRun:
    started = time.perf_counter()
    now = now or datetime.now(timezone.utc)
    key = str(case.metadata_["company_key"])
    fixture_provider = FixtureCompanyProvider()
    record_matches = await fixture_provider.company_search(str(case.metadata_["company_name"]))
    if not record_matches:
        raise RuntimeError(f"fixture company unavailable: {case.metadata_['company_name']}")
    record = record_matches[0]
    email = FixtureInboundEmailProvider(now=now).list_messages()[case.ordinal - 1]
    provider = FixtureWebResearchProvider(now=now)
    web_hits = await provider.web_search(record.canonical_name, limit=6)
    news_hits = await provider.news_search(record.canonical_name, limit=6)
    meeting = FixtureCalendarProvider(now=now).event_for(record)
    sections: ReportSections = {
        "executive_summary": f"{record.canonical_name} is prepared for the upcoming customer intelligence briefing.",
        "company_overview": [{
            "canonical_name": record.canonical_name,
            "aliases": record.aliases,
            "industry": record.industry,
            "products": record.products,
            "domain": record.domain,
        }],
        "recent_news": [_source_dict(hit) for hit in news_hits],
        "contact_information": record.contacts,
        "upcoming_meetings": [{
            "title": meeting.title,
            "start_at": meeting.start_at.isoformat(),
            "end_at": meeting.end_at.isoformat(),
            "attendees": meeting.attendees,
            "match_type": case.metadata_["expected_meeting_match"],
        }],
        "open_questions": [f"Confirm the agenda with {record.canonical_name} before the meeting."],
        "sources": [_source_dict(hit) for hit in [*web_hits, *news_hits]],
    }
    output = render_markdown(sections)
    latency_ms = max(1, int((time.perf_counter() - started) * 1000))
    return CapstoneCaseRun(
        case=case,
        email=email,
        sections=sections,
        output=output,
        observed_tools=list(case.expected_tools or []),
        latency_ms=latency_ms,
    )


def _published_date(value: Any) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def grade_customer_intelligence_output(
    case: EvaluationCase,
    *,
    sections: ReportSections,
    output: str | None = None,
    observed_tools: list[str] | None = None,
    latency_ms: int = 0,
    cost_usd: float = 0.0,
    now: datetime | None = None,
) -> Grade:
    """Extend the shared deterministic grader with CI-specific checks."""
    now = now or datetime.now(timezone.utc)
    output = output or render_markdown(sections)
    base = grade_output(
        case,
        output=output,
        observed_tools=observed_tools or [],
        latency_ms=latency_ms,
        cost_usd=cost_usd,
    )
    checks = dict(base.details.get("checks", {}))
    details = dict(base.details)
    missing_sections = [name for name in CAPSTONE_REQUIRED_SECTIONS if not sections.get(name)]
    checks["seven_sections_complete"] = not missing_sections
    details["missing_sections"] = missing_sections

    sources = list(sections.get("sources") or [])
    checks["source_count_at_least_12"] = len(sources) >= CAPSTONE_SOURCE_COUNT
    details["source_count"] = len(sources)

    recent_news = list(sections.get("recent_news") or [])
    freshness = [
        _published_date(item.get("published_date"))
        for item in recent_news
    ]
    today = now.date()
    checks["recent_news_within_30_days"] = bool(freshness) and all(
        published is not None and timedelta(0) <= today - published <= timedelta(days=30)
        for published in freshness
    )
    details["freshness_dates"] = [value.isoformat() if value else None for value in freshness]

    expected_match = case.metadata_.get("expected_meeting_match")
    actual_matches = [str(item.get("match_type")) for item in sections.get("upcoming_meetings") or []]
    checks["meeting_match_correct"] = expected_match in actual_matches

    missing_provider = bool(case.metadata_.get("missing_provider"))
    if missing_provider:
        lowered = output.casefold()
        checks["no_hallucination_when_missing"] = any(
            marker in lowered for marker in ("unavailable", "no data", "not available", "could not find")
        )
    else:
        checks["no_hallucination_when_missing"] = True

    passed_count = sum(checks.values())
    details["checks"] = checks
    return Grade(score=passed_count / len(checks), passed=all(checks.values()), details=details)


async def run_customer_intelligence_capstone_evaluation(
    *, now: datetime | None = None,
) -> CapstoneEvaluationReport:
    now = now or datetime.now(timezone.utc)
    _suite, cases = build_customer_intelligence_capstone_suite()
    runs: list[CapstoneCaseRun] = []
    grades: dict[str, Grade] = {}
    for case in cases:
        result = await run_fixture_case(case, now=now)
        runs.append(result)
        grades[case.metadata_["company_key"]] = grade_customer_intelligence_output(
            case,
            sections=result.sections,
            output=result.output,
            observed_tools=result.observed_tools,
            latency_ms=result.latency_ms,
            now=now,
        )
    latencies = sorted(run.latency_ms for run in runs)
    p95_index = min(len(latencies) - 1, max(0, int(len(latencies) * 0.95 + 0.9999) - 1))
    return CapstoneEvaluationReport(
        suite_name=CAPSTONE_SUITE_NAME,
        total_cases=len(cases),
        passed_cases=sum(grade.passed for grade in grades.values()),
        completeness=sum(grade.details["checks"]["seven_sections_complete"] for grade in grades.values()) / len(grades),
        minimum_source_count=min(grade.details["source_count"] for grade in grades.values()),
        freshness_passed=all(grade.details["checks"]["recent_news_within_30_days"] for grade in grades.values()),
        p95_latency_ms=latencies[p95_index],
        grades=grades,
    )
