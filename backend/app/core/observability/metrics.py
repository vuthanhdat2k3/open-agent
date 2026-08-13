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
llm_observability_events_total = Counter(
    "llm_observability_events_total",
    "LLM observability events emitted by observation kind",
    ["kind"],
)
llm_observability_export_failures_total = Counter(
    "llm_observability_export_failures_total",
    "LLM observability sink export failures",
    ["sink"],
)
llm_observability_redactions_total = Counter(
    "llm_observability_redactions_total",
    "LLM observability redactions by observation kind",
    ["kind"],
)
llm_observability_dropped_events_total = Counter(
    "llm_observability_dropped_events_total",
    "LLM observability events dropped by reason",
    ["reason"],
)

queue_depth = Histogram("queue_depth", "Observed queue depth")
quota_admission_total = Counter(
    "quota_admission_total",
    "Quota admission decisions",
    ["limit_type", "decision"],
)
chat_finalization_total = Counter(
    "chat_finalization_total",
    "Chat finalization outcomes",
    ["outcome"],  # direct | retry | tool_result_fallback | incomplete
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

# --- Chat event bus ---------------------------------------------------------
# Live chat streaming fans out over Redis pub/sub with the durable event log as
# the replay/fallback path. When the bus fails the stream degrades to database
# polling, which is correct but adds latency â€” so the failure has to be visible
# in metrics rather than only showing up as a user complaint about lag.
# `operation` is bounded: publish | subscribe.
chat_event_bus_failures_total = Counter(
    "chat_event_bus_failures_total",
    "Chat event bus (Redis pub/sub) failures by operation",
    ["operation"],
)
chat_event_stream_transport_total = Counter(
    "chat_event_stream_transport_total",
    "Chat event stream connections by transport actually used",
    ["transport"],  # pubsub | polling
)
# Time from the agent loop recording an event to a follower actually holding it,
# labelled by the transport that delivered it. This deliberately excludes model
# latency: it starts at record(), so a slow first token does not inflate it and
# the pubsub-vs-polling comparison stays apples-to-apples. Buckets are ms-scale
# because pubsub should land under ~10ms while polling is bounded by its poll
# interval (25ms active, up to 250ms idle).
chat_event_fanout_seconds = Histogram(
    "chat_event_fanout_seconds",
    "Seconds from recording a chat event to delivering it to a follower",
    ["transport"],
    buckets=(0.0005, 0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0),
)

# --- Customer Intelligence (M6) ---------------------------------------------
# Bounded label sets on purpose: `result` and `trigger` are low cardinality.
# Never include the tenant/org id or the connection id here - CI syncs happen per
# org and a per-org series set would grow without limit and blow up Prometheus.
ci_syncs_total = Counter(
    "ci_syncs_total",
    "Customer-intelligence email syncs by result",
    ["result"],  # success | error
)
ci_cases_ingested_total = Counter(
    "ci_cases_ingested_total",
    "Customer-intelligence research cases ingested",
    ["trigger"],  # manual | scheduled
)
ci_sync_duration_seconds = Histogram(
    "ci_sync_duration_seconds",
    "Customer-intelligence sync duration in seconds",
)
ci_approval_age_seconds = Histogram(
    "ci_approval_age_seconds",
    "Customer-intelligence delivery-approval age in seconds, bucketed by the decision that resolved it",
    ["decision"],  # approved | rejected | expired
)


def mount_metrics(app) -> None:
    Instrumentator().instrument(app).expose(app, endpoint="/metrics")

# --- Durable scheduled jobs and CI retry ------------------------------------
job_schedule_tick_total = Counter(
    "job_schedule_tick_total",
    "Scheduled job ticks by job key and result",
    ["job_key", "result"],
)
ci_case_retry_total = Counter(
    "ci_case_retry_total",
    "Customer-intelligence case retries by trigger and outcome",
    ["trigger", "outcome"],
)
ci_dead_letter_gauge = Gauge(
    "ci_dead_letter_cases",
    "Current number of Customer Intelligence cases in DEAD_LETTER",
)
