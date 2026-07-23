from __future__ import annotations

from prometheus_client import Counter, Histogram
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


def mount_metrics(app) -> None:
    Instrumentator().instrument(app).expose(app, endpoint="/metrics")

