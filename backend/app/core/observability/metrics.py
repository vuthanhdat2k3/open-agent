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
# --- GenAI (M13) ------------------------------------------------------------
# Label sets stay bounded on purpose: org/model/tool are low-cardinality,
# whereas session_id or agent_id would grow without limit and blow up the
# Prometheus series count.
gen_ai_client_token_usage = Histogram(
    "gen_ai_client_token_usage",
    "LLM token usage per call",
    ["org_id", "model", "token_type"],
)
gen_ai_operation_duration_seconds = Histogram(
    "gen_ai_operation_duration_seconds",
    "GenAI operation duration in seconds",
    ["org_id", "operation", "model"],
)
guardrail_events_total = Counter(
    "guardrail_events_total",
    "Guardrail decisions by kind and outcome",
    ["org_id", "kind", "outcome"],
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
