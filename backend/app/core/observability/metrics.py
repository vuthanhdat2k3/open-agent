from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram
from prometheus_fastapi_instrumentator import Instrumentator

tool_calls_total = Counter(
    "tool_calls_total",
    "Tool calls by tool name and status",
    ["tool_name", "status"],
)
tool_call_duration_seconds = Histogram(
    "tool_call_duration_seconds",
    "Tool call duration in seconds",
    ["tool_name"],
)
agent_run_cost_usd_total = Counter(
    "agent_run_cost_usd_total",
    "Estimated agent run cost in USD",
    ["org_id"],
)
workflow_run_duration_seconds = Histogram(
    "workflow_run_duration_seconds",
    "Workflow run duration in seconds",
)
sandbox_executions_total = Counter(
    "sandbox_executions_total",
    "Sandbox executions by status",
    ["status"],
)
queue_depth = Histogram("queue_depth", "Observed queue depth")
quota_admission_total = Counter(
    "quota_admission_total",
    "Quota admission decisions",
    ["limit_type", "decision"],
)
quota_backend_failures_total = Counter(
    "quota_backend_failures_total",
    "Quota backend failures",
    ["operation"],
)
quota_active_run_leases = Gauge(
    "quota_active_run_leases",
    "Last observed active run lease count",
)


def mount_metrics(app) -> None:
    Instrumentator().instrument(app).expose(app, endpoint="/metrics")
