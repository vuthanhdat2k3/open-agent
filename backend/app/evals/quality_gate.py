from __future__ import annotations


def quality_gate_passes(
    *,
    pass_rate: float,
    min_pass_rate: float,
    latency_delta: float | None = None,
    max_latency_regression_ms: float | None = None,
    cost_delta: float | None = None,
    max_cost_regression_usd: float | None = None,
) -> bool:
    if pass_rate < min_pass_rate:
        return False
    if (
        max_latency_regression_ms is not None
        and latency_delta is not None
        and latency_delta > max_latency_regression_ms
    ):
        return False
    return not (
        max_cost_regression_usd is not None
        and cost_delta is not None
        and cost_delta > max_cost_regression_usd
    )
