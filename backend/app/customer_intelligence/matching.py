from __future__ import annotations

import re

from app.customer_intelligence.contracts import (
    CalendarEvent,
    CompanyRecord,
    MeetingMatch,
    NormalizedEmail,
)
from app.customer_intelligence.providers.research import CompanyProvider

_TOKEN_SPLIT_RE = re.compile(r"[^a-z0-9]+")


def extract_candidate_names(text: str) -> list[str]:
    """Return plausible company-name candidates from email text.

    Matches well-formed company names: 2+ capitalized tokens that appear in
    the subject or body (e.g. "Acme Corporation", "Stark Industries").
    Rejects single tokens, common filler words, and names with digits only.
    """
    stop = {
        "the", "and", "for", "with", "from", "your", "our", "this", "that",
        "inc", "llc", "corp", "co", "ltd", "gmbh", "reply", "re", "fw", "fwd",
        "hello", "hi", "dear", "please", "thank", "thanks", "regards", "best",
        "sincerely", "customer", "intelligence", "team", "subject",
    }
    candidates: list[str] = []
    for match in re.finditer(r"\b([A-Z][a-zA-Z0-9&'.-]*(?:\s+[A-Z][a-zA-Z0-9&'.-]*)+)\b", text):
        name = match.group(1).strip()
        words = [w for w in _TOKEN_SPLIT_RE.split(name.lower()) if w]
        if len(words) < 2 or all(w in stop for w in words):
            continue
        if name not in candidates:
            candidates.append(name)
    return candidates[:5]


async def match_companies(email: NormalizedEmail, company_provider: CompanyProvider) -> list[CompanyRecord]:
    """Match a normalized email to known companies.

    Candidates come from the subject + sender display name + first 2000 chars
    of the body. Each candidate is queried against the company provider; the
    provider's fuzzy lookup is authoritative (unknown companies return []).
    """
    text = " ".join(
        filter(
            None,
            [email.subject, email.sender_name or "", email.body_text[:2000]],
        )
    )
    candidates = extract_candidate_names(text)
    records: list[CompanyRecord] = []
    for name in candidates:
        for rec in await company_provider.company_search(name, limit=1):
            if rec.company_id not in {r.company_id for r in records}:
                records.append(rec)
    return records


def match_meetings(events: list[CalendarEvent], companies: list[CompanyRecord]) -> list[MeetingMatch]:
    """Match calendar events to known companies by attendee domain and title.

    A ``confirmed_match`` requires the event attendee domain to equal a known
    company domain; ``possible_match`` covers title mentions of a canonical
    name/alias. Events are matched to at most one company.
    """
    matches: list[MeetingMatch] = []
    for event in events:
        domains = {a.rsplit("@", 1)[-1].lower() for a in event.attendees if "@" in a}
        matched: tuple[str, list[str]] | None = None
        for company in companies:
            company_domain = (company.domain or "").lower()
            if company_domain and company_domain in domains:
                matched = (company.company_id, ["attendee_domain"])
                break
        if matched is None:
            text = f"{event.title} {event.description or ''}".lower()
            for company in companies:
                names = [company.canonical_name.lower(), *[a.lower() for a in company.aliases]]
                if any(name in text for name in names):
                    matched = (company.company_id, ["title"])
                    break
        if matched is not None:
            company = next(c for c in companies if c.company_id == matched[0])
            matches.append(
                MeetingMatch(
                    event=event,
                    match_type="confirmed_match" if matched[1] == ["attendee_domain"] else "possible_match",
                    confidence=1.0 if matched[1] == ["attendee_domain"] else 0.6,
                    matched_on=matched[1],
                )
            )
    return matches
