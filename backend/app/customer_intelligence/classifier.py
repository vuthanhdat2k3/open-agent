from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from app.customer_intelligence.contracts import NormalizedEmail


@dataclass(frozen=True)
class Classification:
    label: str
    confidence: float
    reason: str


_SPAM_TERMS = re.compile(r"\b(win|winner|prize|casino|viagra|crypto giveaway|unsubscribe)\b", re.I)
_CALENDAR_TERMS = re.compile(r"\b(meeting|meet|call|calendar|schedule|zoom|teams|google meet|họp|lịch)\b", re.I)
_DATE_OR_TIME = re.compile(r"\b(?:\d{1,2}[:.]\d{2}|\d{1,2}/\d{1,2}(?:/\d{2,4})?)\b")
_FREE_MAIL = {"gmail.com", "googlemail.com", "yahoo.com", "outlook.com", "hotmail.com", "icloud.com"}


def classify_email(email: NormalizedEmail) -> Classification:
    if email.injection_flags:
        return Classification("security_risk", 1.0, "guard flagged untrusted instruction content")
    text = f"{email.subject}\n{email.body_text}"[:20_000]
    spam_hits = len(_SPAM_TERMS.findall(text))
    if spam_hits >= 2:
        return Classification("spam", min(0.99, 0.7 + spam_hits * 0.05), "spam indicators matched")
    if _CALENDAR_TERMS.search(text) and _DATE_OR_TIME.search(text):
        return Classification("calendar", 0.9, "meeting intent and date/time detected")
    if email.sender_domain.lower() not in _FREE_MAIL and email.sender_domain:
        return Classification("customer", 0.75, "sender uses an organizational domain")
    return Classification("normal", 0.7, "no high-risk or special routing signal")


def extract_calendar_payload(email: NormalizedEmail) -> dict[str, Any] | None:
    """Extract only explicit bounded date/time signals; never infer a meeting."""
    text = f"{email.subject}\n{email.body_text}"[:20_000]
    time_match = re.search(r"\b([01]?\d|2[0-3])[:.]([0-5]\d)\b", text)
    date_match = re.search(r"\b(20\d{2})[-/](\d{1,2})[-/](\d{1,2})\b", text)
    if date_match is None:
        date_match = re.search(r"\b(\d{1,2})[/-](\d{1,2})(?:[/-](20\d{2}))?\b", text)
        if date_match is None:
            return None
        day, month, year = int(date_match.group(1)), int(date_match.group(2)), date_match.group(3)
        year = int(year) if year else datetime.now(timezone.utc).year
    else:
        year, month, day = (int(part) for part in date_match.groups())
    if time_match is None:
        return None
    hour, minute = int(time_match.group(1)), int(time_match.group(2))
    try:
        start = datetime(year, month, day, hour, minute, tzinfo=timezone.utc)
    except ValueError:
        return None
    end = start + timedelta(hours=1)
    return {
        "summary": email.subject[:500] or "Meeting from email",
        "start": start.isoformat(),
        "end": end.isoformat(),
        "description": f"Created from email {email.provider_message_id}",
        "attendees": [email.sender_email] if "@" in email.sender_email else [],
    }
