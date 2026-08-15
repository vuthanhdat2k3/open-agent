from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.evals.customer_intelligence_capstone import (
    CAPSTONE_MAX_LATENCY_MS,
    CAPSTONE_SOURCE_COUNT,
    CAPSTONE_SUITE_NAME,
    build_customer_intelligence_capstone_suite,
    grade_customer_intelligence_output,
    run_customer_intelligence_capstone_evaluation,
)


@pytest.mark.asyncio
async def test_customer_intelligence_capstone_evaluation_runs_six_deterministic_cases(capsys) -> None:
    now = datetime(2026, 8, 15, 0, 0, tzinfo=timezone.utc)
    report = await run_customer_intelligence_capstone_evaluation(now=now)

    print(
        f"suite={report.suite_name} cases={report.total_cases} "
        f"completeness={report.completeness:.0%} "
        f"min_sources={report.minimum_source_count} "
        f"freshness={report.freshness_passed} p95_latency_ms={report.p95_latency_ms}"
    )
    captured = capsys.readouterr()
    assert CAPSTONE_SUITE_NAME in captured.out
    assert report.total_cases == 6
    assert report.passed_cases == 6
    assert report.completeness == 1.0
    assert report.minimum_source_count >= CAPSTONE_SOURCE_COUNT
    assert report.freshness_passed
    assert report.p95_latency_ms <= CAPSTONE_MAX_LATENCY_MS
    assert report.passed


def test_capstone_suite_uses_shared_evaluation_case_contract() -> None:
    suite, cases = build_customer_intelligence_capstone_suite()

    assert suite.name == CAPSTONE_SUITE_NAME
    assert len(cases) == 6
    assert [case.ordinal for case in cases] == list(range(1, 7))
    assert all(case.metadata_["fixture"] for case in cases)
    assert all("company_search" in (case.expected_tools or []) for case in cases)


def test_missing_provider_result_must_say_data_is_unavailable() -> None:
    _suite, cases = build_customer_intelligence_capstone_suite()
    case = cases[0]
    case.metadata_["missing_provider"] = True
    sections = {
        "executive_summary": "Research unavailable; no data was returned.",
        "company_overview": [{"canonical_name": "Unknown company"}],
        "recent_news": [{"title": "No data", "published_date": "2026-08-14"}],
        "contact_information": [{"name": "Not available"}],
        "upcoming_meetings": [{"match_type": case.metadata_["expected_meeting_match"]}],
        "open_questions": ["Research unavailable"],
        "sources": [{"url": "https://fixture.example/source", "title": "No data"}] * 12,
    }
    passing = grade_customer_intelligence_output(case, sections=sections, output="Research unavailable; no data was returned.", now=datetime(2026, 8, 15, tzinfo=timezone.utc))
    assert passing.details["checks"]["no_hallucination_when_missing"]

    failing = grade_customer_intelligence_output(case, sections=sections, output="The company is a global leader.", now=datetime(2026, 8, 15, tzinfo=timezone.utc))
    assert not failing.details["checks"]["no_hallucination_when_missing"]
