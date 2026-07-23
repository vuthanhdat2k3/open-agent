from __future__ import annotations

import math
import re
from dataclasses import dataclass

REDACTION = "[REDACTED_SECRET]"

_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")),
    ("private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    (
        "generic_api_key",
        re.compile(
            r"(?i)\b(api[_-]?key|secret|token|password)\s*[:=]\s*['\"]?([A-Za-z0-9_\-]{24,})"
        ),
    ),
]
_LONG_TOKEN = re.compile(r"\b[A-Za-z0-9_\-+/=]{24,}\b")


@dataclass(frozen=True)
class SecretFinding:
    kind: str
    start: int
    end: int


def _entropy(value: str) -> float:
    if not value:
        return 0.0
    counts = {ch: value.count(ch) for ch in set(value)}
    length = len(value)
    return -sum((count / length) * math.log2(count / length) for count in counts.values())


def scan_and_redact(text: str) -> tuple[str, list[SecretFinding]]:
    spans: list[tuple[int, int, str]] = []

    for kind, pattern in _PATTERNS:
        for match in pattern.finditer(text):
            start, end = match.span(2) if kind == "generic_api_key" and match.lastindex else match.span()
            spans.append((start, end, kind))

    for match in _LONG_TOKEN.finditer(text):
        value = match.group(0)
        if len(value) > 20 and _entropy(value) >= 4.2:
            spans.append((match.start(), match.end(), "high_entropy_token"))

    if not spans:
        return text, []

    findings = [SecretFinding(kind=kind, start=start, end=end) for start, end, kind in spans]
    spans.sort(key=lambda item: (item[0], -(item[1] - item[0])))
    merged: list[tuple[int, int, str]] = []
    for start, end, kind in spans:
        if merged and start <= merged[-1][1]:
            prev_start, prev_end, prev_kind = merged[-1]
            merged[-1] = (prev_start, max(prev_end, end), prev_kind)
        else:
            merged.append((start, end, kind))

    clean_parts: list[str] = []
    cursor = 0
    for start, end, _kind in merged:
        clean_parts.append(text[cursor:start])
        clean_parts.append(REDACTION)
        cursor = end
    clean_parts.append(text[cursor:])
    return "".join(clean_parts), findings
