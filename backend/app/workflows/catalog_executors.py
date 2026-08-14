"""Business executors for the built-in workflow catalog.

The catalog must never report success from the generic DAG placeholder. These
executors read canonical CI data and return bounded, auditable output. External
side effects remain outside this module and continue through approval/delivery.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utc_now
from app.models.customer_intelligence import InboundEmail, Meeting, ResearchCase
from app.models.workflow_installation import WorkflowInstallation

REPORT_TEMPLATES = {
    "morning-command-center": timedelta(days=1),
    "follow-up-radar": timedelta(days=14),
    "meeting-preparation": timedelta(days=7),
    "end-of-day-client-digest": timedelta(days=1),
    "weekly-account-review": timedelta(days=7),
}


async def execute_catalog_report(
    db: AsyncSession,
    *,
    installation: WorkflowInstallation,
    trigger: str,
) -> dict[str, Any]:
    """Build a deterministic report from persisted data for one installation.

    This intentionally avoids one LLM call per email. A future synthesis step
    can consume this bounded snapshot under an explicit cost budget without
    changing the data selection or safety boundary.
    """
    window = REPORT_TEMPLATES.get(installation.template_key)
    if window is None:
        raise RuntimeError(f"no report executor for template {installation.template_key}")

    now = utc_now()
    emails = list(
        (
            await db.scalars(
                select(InboundEmail)
                .where(
                    InboundEmail.org_id == installation.org_id,
                    InboundEmail.created_by_user_id == installation.owner_user_id,
                    InboundEmail.received_at >= now - window,
                    InboundEmail.routing_status.not_in(["ignored", "quarantined"]),
                )
                .order_by(InboundEmail.received_at.desc(), InboundEmail.id.desc())
                .limit(100)
            )
        ).all()
    )
    cases = list(
        (
            await db.scalars(
                select(ResearchCase)
                .where(
                    ResearchCase.org_id == installation.org_id,
                    ResearchCase.created_by_user_id == installation.owner_user_id,
                    ResearchCase.created_at >= now - window,
                )
                .order_by(ResearchCase.created_at.desc(), ResearchCase.id.desc())
                .limit(50)
            )
        ).all()
    )
    meetings = list(
        (
            await db.scalars(
                select(Meeting)
                .join(ResearchCase, ResearchCase.id == Meeting.case_id)
                .where(
                    Meeting.org_id == installation.org_id,
                    ResearchCase.created_by_user_id == installation.owner_user_id,
                    Meeting.start_at >= now,
                    Meeting.start_at <= now + timedelta(days=14),
                )
                .order_by(Meeting.start_at.asc(), Meeting.id.asc())
                .limit(50)
            )
        ).all()
    )

    report: dict[str, Any] = {
        "kind": "catalog_report",
        "template_key": installation.template_key,
        "template_version": installation.template_version,
        "generated_at": now.isoformat() + "Z",
        "trigger": trigger,
        "window": {
            "from": (now - window).isoformat() + "Z",
            "to": now.isoformat() + "Z",
        },
        "sections": {},
        "counts": {"emails": len(emails), "research_cases": len(cases), "meetings": len(meetings)},
        "warnings": [],
    }

    if installation.template_key == "meeting-preparation":
        report["sections"] = {
            "upcoming_meetings": [_meeting_view(item) for item in meetings],
            "research_cases": [_case_view(item) for item in cases[:20]],
        }
    elif installation.template_key == "follow-up-radar":
        report["sections"] = {"follow_up_candidates": [_email_view(item) for item in emails[:50]]}
    elif installation.template_key == "weekly-account-review":
        report["sections"] = {
            "customer_activity": [_email_view(item) for item in emails[:50]],
            "research_cases": [_case_view(item) for item in cases[:30]],
            "upcoming_meetings": [_meeting_view(item) for item in meetings[:20]],
        }
    else:
        report["sections"] = {
            "important_email": [_email_view(item) for item in emails[:30]],
            "research_cases": [_case_view(item) for item in cases[:20]],
            "upcoming_meetings": [_meeting_view(item) for item in meetings[:20]],
        }

    if not emails:
        report["warnings"].append("No eligible email activity was found in the selected window")
    if installation.template_key == "meeting-preparation" and not meetings:
        report["warnings"].append("No upcoming meetings were found in persisted calendar data")
    return report


def _email_view(email: InboundEmail) -> dict[str, Any]:
    return {
        "id": email.id,
        "received_at": email.received_at.isoformat() + "Z",
        "sender": email.sender_email,
        "subject": email.subject,
        "classification": email.classification,
        "routing_status": email.routing_status,
        "summary": (email.classification_json or {}).get("summary") or email.subject,
    }


def _case_view(case: ResearchCase) -> dict[str, Any]:
    return {
        "id": case.id,
        "company_name": case.company_name,
        "company_domain": case.company_domain,
        "status": case.status,
        "confidence": case.confidence,
    }


def _meeting_view(meeting: Meeting) -> dict[str, Any]:
    return {
        "id": meeting.id,
        "title": meeting.title,
        "start_at": meeting.start_at.isoformat() + "Z" if meeting.start_at else None,
        "end_at": meeting.end_at.isoformat() + "Z" if meeting.end_at else None,
        "attendees": meeting.attendees or [],
        "match_type": meeting.match_type,
        "confidence": meeting.confidence,
    }
