from __future__ import annotations

import re
from dataclasses import dataclass

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
