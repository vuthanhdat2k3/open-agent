"""Redaction helpers for observability payloads.

The functions in this module return new values and never mutate runtime
messages, tool arguments, results, or metadata.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.core.guardrails.secrets import REDACTION, scan_and_redact

REDACTION_PII = "[REDACTED_PII]"
REDACTION_SECRET = REDACTION

_SENSITIVE_KEY = re.compile(
    r"(?i)(^|[_-])(api[_-]?key|access[_-]?token|refresh[_-]?token|secret|password|authorization|credential)([_-]|$)"
)
_PII_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("email", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    ("phone", re.compile(r"(?<!\d)(?:\+?\d[\d .()\-]{7,}\d)(?!\d)")),
)


@dataclass
class RedactionStats:
    count: int = 0
    kinds: set[str] = field(default_factory=set)
    failed: bool = False

    def add(self, kind: str, count: int = 1) -> None:
        self.count += count
        self.kinds.add(kind)

    def merge(self, other: RedactionStats) -> None:
        self.count += other.count
        self.kinds.update(other.kinds)
        self.failed = self.failed or other.failed

    def as_metadata(self, *, content_capture: bool) -> dict[str, Any]:
        return {
            "redaction_applied": self.count > 0,
            "redaction_count": self.count,
            "redaction_kinds": sorted(self.kinds),
            "redaction_failed": self.failed,
            "content_capture": content_capture,
        }


def _redact_string(value: str) -> tuple[str, RedactionStats]:
    stats = RedactionStats()
    try:
        safe, findings = scan_and_redact(value)
        if findings:
            stats.count += len(findings)
            stats.kinds.update(f.kind for f in findings)
        for kind, pattern in _PII_PATTERNS:
            safe, substitutions = pattern.subn(REDACTION_PII, safe)
            if substitutions:
                stats.add(kind, substitutions)
        return safe, stats
    except Exception:  # noqa: BLE001
        return REDACTION, RedactionStats(count=1, kinds={"sanitizer_failure"}, failed=True)


def redact_payload(value: Any, *, _key: str | None = None) -> tuple[Any, RedactionStats]:
    """Deep-copy and redact arbitrary JSON-like provider payloads."""
    stats = RedactionStats()
    if isinstance(value, str):
        if _key and _SENSITIVE_KEY.search(_key):
            return REDACTION, RedactionStats(count=1, kinds={"sensitive_field"})
        return _redact_string(value)
    if isinstance(value, dict):
        clean: dict[Any, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            safe_item, child = redact_payload(item, _key=key_text)
            clean[key] = safe_item
            stats.merge(child)
        return clean, stats
    if isinstance(value, list):
        clean_list = []
        for item in value:
            safe_item, child = redact_payload(item)
            clean_list.append(safe_item)
            stats.merge(child)
        return clean_list, stats
    if isinstance(value, tuple):
        safe_list, child = redact_payload(list(value))
        return tuple(safe_list), child
    if isinstance(value, set):
        safe_list, child = redact_payload(list(value))
        return set(safe_list), child
    return value, stats
