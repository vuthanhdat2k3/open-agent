from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import regex

from app.models.evaluation import EvaluationCase


@dataclass(frozen=True)
class Grade:
    score: float
    passed: bool
    details: dict[str, Any]


def _normalize(value: str) -> str:
    return " ".join(value.split()).casefold()


def grade_output(
    case: EvaluationCase,
    *,
    output: str,
    observed_tools: list[str],
    latency_ms: int,
    cost_usd: float,
) -> Grade:
    checks: dict[str, bool] = {}

    if case.expected_output is not None:
        checks["exact_match"] = _normalize(output) == _normalize(case.expected_output)

    normalized_output = output.casefold()
    for index, required in enumerate(case.required_substrings or []):
        checks[f"required_substring:{index}"] = required.casefold() in normalized_output

    observed = set(observed_tools)
    for tool in case.expected_tools or []:
        checks[f"expected_tool:{tool}"] = tool in observed

    regex_errors: dict[str, str] = {}
    for index, pattern in enumerate(case.forbidden_patterns or []):
        key = f"forbidden_pattern:{index}"
        try:
            checks[key] = (
                regex.search(
                    pattern,
                    output,
                    flags=regex.IGNORECASE,
                    timeout=0.05,
                )
                is None
            )
        except (regex.error, TimeoutError) as exc:
            checks[key] = False
            regex_errors[pattern] = str(exc)

    if case.max_latency_ms is not None:
        checks["max_latency_ms"] = latency_ms <= case.max_latency_ms
    if case.max_cost_usd is not None:
        checks["max_cost_usd"] = cost_usd <= case.max_cost_usd

    if not checks:
        checks["execution_succeeded"] = True
    passed_count = sum(checks.values())
    score = passed_count / len(checks)
    details: dict[str, Any] = {"checks": checks}
    if regex_errors:
        details["regex_errors"] = regex_errors
    return Grade(score=score, passed=all(checks.values()), details=details)
