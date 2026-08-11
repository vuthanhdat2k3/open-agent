# LLM Observability (Langfuse) — Design Spec

Date: 2026-08-11
Status: Approved by user, pending implementation plan

## 1. Problem

OpenAgent has OpenTelemetry GenAI spans (`backend/app/core/observability/genai.py`)
that carry model name, token usage, and duration, but message content
capture is opt-in and off by default, and there is no unified record of a
single LLM generation's full input/output alongside its tool calls. LLM
calls are made from five independent call sites — `agent_loop.py`,
`compactor.py`, `core/memory/tiers.py`, `workflow_service.py`, and any
sub-agent delegation — each constructing a driver via `build_driver()` and
calling `.complete()`/`.stream()` directly. There is no way today to open one
trace and see: the system prompt, the user prompt, every tool call and its
result, retries/fallbacks, and the final response, for one agent run.

## 2. Goal

Add a provider-neutral LLM observability layer that instruments every real
LLM generation exactly once (at the driver level, not scattered through
business logic), redacts secrets/PII before persisting anything, and ships
the redacted trace to a self-hosted Langfuse instance. A trace should show
the full hierarchy of one agent run — planner/model generations, tool calls,
memory/compaction steps, retries/fallbacks — with token usage, cost,
latency, and status on every node.

## 3. Non-goals

- No trace for provider discovery, health checks, model availability
  checks, capability probing, or periodic test requests (`ProviderService`,
  `ModelDiscoveryService`). Those emit `provider/model/status/latency/error`
  to metrics/logs only, per the existing Prometheus setup.
- No change to the existing OTel GenAI spans/metrics — they keep running
  independently. This layer is additive, not a replacement.
- No Langfuse prompt-management or evaluation features in v1 (tracing only).
- No UI changes to the OpenAgent debug view beyond adding a link/trace_id
  reference; a full embedded trace viewer is out of scope for v1.
- No fork or storage-architecture change to Langfuse; deployed as documented
  upstream, pinned to a specific release.
- No cross-org trace visibility; every trace is scoped to the org that owns
  the agent run, same as every other repository/query in the codebase.

## 4. Architecture

```
Agent / Planner / Workflow / Memory / Tool runner
                │
                ▼
        ObservabilityContext (TraceContext + observation lifecycle)
                │
                ▼
        Redaction / Sanitization (secrets + PII, deep-walks all payloads)
                │
                ▼
        ObservabilitySink (protocol)
                │
      ┌─────────┴─────────┐
      ▼                   ▼
LangfuseSink          NoopSink (default off / sink unavailable)
      │
      ▼
Langfuse (self-hosted, official Docker Compose deployment)
      │
┌─────┼─────────┬─────────────┐
▼     ▼         ▼             ▼
Web  Worker  Postgres     ClickHouse + Redis/Valkey + S3/blob store
```

Business logic never imports `langfuse`. The only integration points are:

1. `build_driver()` returns an `ObservableLLMDriver` wrapping the real
   driver — this is the single place every LLM call is instrumented.
2. The tool runner (`execute_tool_call()` call sites in `agent_loop.py` /
   `core/workflow/engine.py`) gets one hook to open/close a tool observation,
   since a driver cannot see the tool result — that happens outside the
   driver call.

If Langfuse is replaced later (OTel + Tempo/Grafana, another vendor), only
`LangfuseSink` changes. `ObservabilityContext`, `TraceContext`,
`GenerationRecord`, `ToolObservation`, and every call site stay the same.

### 4.1 Trace / session mapping

- `root_run_id` (already the stable id threaded through `agent_loop.py`,
  `chat_events.py`, and workflow runs) maps 1:1 to Langfuse `trace_id`. It is
  generated once per chat run / workflow run and does not change across
  retries, tool calls, or reconnects, so reloading a chat or replaying a run
  lands on the same trace.
- `session_id` (the OpenAgent chat `Session`) maps to Langfuse `session_id`,
  used purely for grouping multiple traces of the same conversation in the
  Langfuse UI. It is *not* a parent of the trace in the internal contract —
  `TraceContext` carries both ids independently, and nothing in
  `ObservabilityContext` assumes a session contains traces or vice versa.
  This keeps the internal model correct even for entry points with no
  session (a one-shot workflow run, a scheduled job).
- Sub-agent delegation (`call_agent`) and workflow node runs share the same
  `root_run_id`/trace as their parent; they add a new observation level, not
  a new trace — one full delegation chain is one trace.

### 4.2 Internal contract (`backend/app/core/observability/llm_trace.py`)

```python
@dataclass
class TraceContext:
    trace_id: str                    # = root_run_id
    session_id: str | None
    org_id: str
    user_id: str | None
    agent_id: str | None
    agent_release_id: str | None
    parent_observation_id: str | None
    content_capture: bool            # resolved policy, see 4.5
    sampling_rate: float
    metadata: dict[str, Any]

class ObservationHandle(Protocol):
    observation_id: str
    trace_id: str
    parent_id: str | None
    kind: Literal["span", "generation", "event"]

    def finish_success(self, **fields: Any) -> None: ...
    def finish_error(self, exc: BaseException, **fields: Any) -> None: ...
    def finish_cancelled(self, **fields: Any) -> None: ...
```

`finish_*` is idempotent: the first call wins and sets a `_finished` flag;
any subsequent call (e.g. an `except` block finishing an observation that a
`finally` block also tries to finish) is a no-op. This is what makes
retry/cancellation paths safe — a generation is never double-recorded.

```python
@dataclass
class GenerationRecord:
    name: str                        # "planner", "final-response", "compactor", ...
    provider: str
    model: str
    input: Any                       # pre-redaction; redacted before sink.emit
    output: Any | None
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    cost_usd: float | None
    latency_ms: int
    status: Literal["started", "success", "error", "cancelled"]
    error: dict[str, Any] | None
    metadata: dict[str, Any]
    retry_index: int = 0
    fallback_from: str | None = None # model name of the attempt this replaces

@dataclass
class ToolObservation:
    tool_name: str
    tool_call_id: str | None
    arguments: Any
    result: Any | None
    status: Literal["started", "success", "error", "denied", "cancelled"]
    duration_ms: int | None
    error: dict[str, Any] | None
    metadata: dict[str, Any]
```

Neither dataclass references Langfuse types. `LangfuseSink` is the only
module that imports the `langfuse` SDK and maps these into
generation/span/event observations.

### 4.3 `ObservableLLMDriver` — the single LLM instrumentation point

```python
class ObservableLLMDriver:
    """Wraps any LLMDriver; forwards every call, records one generation."""

    def __init__(self, inner: LLMDriver, ctx: TraceContext, sink: ObservabilitySink):
        self._inner = inner
        self._ctx = ctx
        self._sink = sink

    async def complete(self, messages, **kwargs):
        obs = self._sink.start_generation(self._ctx, name=..., provider=..., model=..., input=messages)
        try:
            content, usage, tool_calls = await self._inner.complete(messages, **kwargs)
            obs.finish_success(output=content, usage=usage, tool_calls=tool_calls)
            return content, usage, tool_calls
        except Exception as exc:
            obs.finish_error(exc)
            raise

    def stream(self, messages, **kwargs):
        # Same shape, but accumulates content/usage/tool_calls across the
        # async generator and finishes the generation once the stream ends
        # or raises — never once per chunk.
        ...
```

`build_driver(provider, model)` in `core/providers/factory.py` becomes:

```python
def build_driver(provider, model, *, ctx: TraceContext | None = None) -> LLMDriver:
    inner = _build_raw_driver(provider, model)   # today's factory logic, unchanged
    if ctx is None:
        return inner                              # discovery/health-check path: no trace
    sink = get_observability_sink()
    return ObservableLLMDriver(inner, ctx, sink)
```

Callers that pass `ctx` (agent loop, compactor, memory tiers, workflow
service, sub-agent delegation) get a traced driver automatically. Callers
that build a driver for discovery/testing (`ProviderService`,
`ModelDiscoveryService`) omit `ctx` and get the raw driver — satisfying the
non-goal in §3 without a second code path to maintain.

Retries/fallbacks are the caller's responsibility (as today), but each
attempt calls `complete`/`stream` again, so each attempt is its own
`GenerationRecord` with `retry_index` incremented and `fallback_from` set to
the previous attempt's model — no attempt overwrites another's observation.

### 4.4 Tool observation hook

Added at the two call sites that invoke `execute_tool_call()`
(`agent_loop.py`, `core/workflow/engine.py`):

```python
tool_obs = ctx.start_tool_observation(name=spec.name, call_id=call_id, arguments=args)
try:
    result = await execute_tool_call(spec, args, tool_ctx)
    tool_obs.finish_success(result=result)
except Exception as exc:
    tool_obs.finish_error(exc)
    raise
```

This nests under the generation that produced the tool call (the parent
`observation_id` is threaded through `TraceContext`), matching the hierarchy
in §4.6. `ctx` is `None`-safe: when observability is disabled the call is a
no-op (see `NoopSink` in §4.7).

### 4.5 Content-capture / sampling policy precedence

`content_capture` on `TraceContext` is a single resolved boolean, but it is
computed with explicit precedence, evaluated once per run when the context
is built:

```
global policy (config: OPENAGENT_OBSERVABILITY_CAPTURE_CONTENT)
        │  default false in prod, true in dev
        ▼
org-level override (Organization setting, optional)
        │  can only narrow, never widen, the global policy
        ▼
agent-level override (Agent setting, optional)
        │  can only narrow, never widen, the org policy
        ▼
per-request override (e.g. a debug/sampling flag on a chat request)
        │  can only narrow, never widen, the agent policy
        ▼
resolved content_capture
```

A lower level can only turn capture *off* relative to what the level above
allowed; it can never turn capture *on* if a higher level disabled it. This
guarantees a request cannot silently exfiltrate raw content past an
org-level policy that disabled it. Sampling (`sampling_rate`) is independent
of this chain and only decides how many *metadata-only* traces also get full
content — every generation is always traced (name, model, tokens, latency,
status); `sampling_rate` decides what fraction additionally get raw
input/output attached after redaction.

### 4.6 Trace hierarchy example

```
Trace (root_run_id)
└── Agent Run span
    ├── Generation: planner
    │   └── Tool span: search_customer
    ├── Span: memory_retrieval
    ├── Generation: model-response (attempt 0, primary model) [error]
    ├── Generation: model-response (attempt 1, fallback model) [success]
    │   └── Tool span: fetch_order
    ├── Span: compaction
    │   └── Generation: compactor summary
    └── Generation: final-response
```

Sub-agent delegation adds one more level under the parent's tool span (the
`call_agent` tool call), containing its own Agent Run span with the same
`trace_id`.

### 4.7 Redaction pipeline

Runs on a **copy** of every payload before it reaches `ObservabilitySink`;
runtime objects passed to the LLM/tool are never mutated.

```
raw input/output/arguments/result/error/metadata
        │
        ▼
normalize (stringify structured content consistently)
        │
        ▼
secret redaction (API keys, bearer tokens, AWS/GCP/Azure creds,
                   private keys, DB URLs/passwords, provider secrets)
        │
        ▼
PII redaction (email, phone — reuses the existing scan_and_redact from
                app/core/guardrails/secrets.py where patterns overlap;
                extended for the additional secret shapes above)
        │
        ▼
size/serialization safety (truncate + flag oversized payloads instead of
                             dropping the whole event)
        │
        ▼
ObservabilitySink.emit(...)
```

Applied uniformly to: system prompt, user prompt, assistant response, tool
arguments, tool result, exception messages/stack summaries, and metadata
dicts. The redacted copy is what gets logged on error paths too — raw
payloads must never reach a fallback `logger.exception(...)` call either;
any error logging inside the observability layer logs the *redacted*
record.

Metadata recorded alongside every observation:

```json
{
  "redaction_applied": true,
  "redaction_count": 3,
  "content_capture": true,
  "content_truncated": false
}
```

### 4.8 `LangfuseSink`

The only module depending on the `langfuse` Python SDK. Responsibilities:

- Map `TraceContext` → Langfuse trace/session attributes (`trace_id`,
  `session_id`, `user_id`, `metadata`, tags for `org_id`/`agent_id`).
- Map `GenerationRecord` → a Langfuse `generation` observation (model,
  input, output, usage, cost, latency, status/error).
- Map `ToolObservation` → a Langfuse `span` observation (or `event` for
  fire-and-forget notices), nested under its parent observation id.
- Batch and flush asynchronously; never block the caller's request path
  waiting on the Langfuse ingestion API.
- On SDK/network failure: increment a failure counter and drop the event —
  never raise into the caller (see §4.9).

### 4.9 Failure isolation

Observability must never break an LLM request:

- Langfuse unreachable → the LLM call still completes normally; only the
  trace is missing.
- Redaction raising an exception → fail closed on **content** (drop the
  content fields) but still emit the observation with metadata/status/error,
  so a redaction bug degrades observability, not the request.
- Sink queue full → drop the event under a documented policy (drop-oldest),
  never block or apply backpressure to the LLM call.
- Every sink call wrapped so an exception from the sink is caught, logged
  once (rate-limited), and swallowed.
- Shutdown flushes the sink with a bounded deadline; it does not hang app
  shutdown indefinitely.

New metrics (Prometheus, alongside the existing `gen_ai_*` metrics in
`core/observability/metrics.py`):

- `llm_observability_events_total{kind}`
- `llm_observability_export_failures_total{sink}`
- `llm_observability_redactions_total{field}`
- `llm_observability_dropped_events_total{reason}`

### 4.10 Deployment

Self-hosted Langfuse via the official Docker Compose deployment, added as
new services in `docker-compose.yml` (and `docker-compose.observability.yml`
or the existing `observability` profile — decided during implementation
planning, not this spec):

- `langfuse-web`, `langfuse-worker` — pinned to a specific released image
  tag (no `:latest`).
- Storage: a **new dedicated Postgres database** (not the OpenAgent
  application database) to keep Langfuse's schema and migrations isolated
  from `alembic/versions/`; ClickHouse; Redis/Valkey; S3-compatible object
  storage (MinIO, already used for other blob storage in this repo, is a
  candidate — decided during implementation).
- Persistent volumes for every storage component.
- All Langfuse secrets (DB passwords, encryption keys, API keys OpenAgent
  uses to talk to Langfuse) live in `.env`, following the existing
  `.env.example` pattern — never hardcoded in `docker-compose.yml`.
- Backup: documented procedure for Postgres + ClickHouse + object storage
  (exact tooling decided during implementation; must be in the plan).
- Retention: a documented Langfuse retention/TTL setting for old traces,
  configured at the org/project level in Langfuse itself.

## 5. Data flow (end to end)

```
1. agent_loop.py builds TraceContext (root_run_id, org/agent/session ids,
   resolved content_capture) once per run.
2. build_driver(provider, model, ctx=trace_ctx) returns ObservableLLMDriver.
3. Every .complete()/.stream() call opens a GenerationRecord, forwards to
   the real driver, redacts the result, and finishes the observation.
4. Every execute_tool_call() site opens/closes a ToolObservation the same
   way, nested under the generation that requested it.
5. Retries/fallbacks repeat step 3 with retry_index/fallback_from set.
6. ObservabilityContext.emit(...) redacts, then hands the record to the
   configured ObservabilitySink (LangfuseSink in prod, NoopSink if disabled
   or unconfigured).
7. LangfuseSink batches and ships to the self-hosted Langfuse instance;
   failures are isolated per §4.9.
```

## 6. Testing strategy

- Unit tests for the redaction pipeline: known secret shapes (API keys,
  bearer tokens, DB URLs, cloud credentials) are removed from prompts, tool
  arguments/results, and exception messages; PII patterns are redacted;
  non-secret content passes through unchanged.
- Unit tests for `ObservationHandle` idempotency: calling `finish_success`
  then `finish_error` (or any pair) only records the first outcome.
- Unit tests for content-capture precedence: global/org/agent/request
  combinations that assert a lower level can never widen a narrower policy
  above it.
- Unit tests for `ObservableLLMDriver`: wraps a fake inner driver, asserts
  exactly one generation per `complete()`/full `stream()` call (not per
  chunk), correct status on success/error, and correct `retry_index`/
  `fallback_from` across a simulated retry.
- Unit tests for the tool observation hook: success, tool error, and denied
  (risk-tier-blocked) paths each produce exactly one finished observation.
- Failure-isolation tests: a `LangfuseSink` that always raises must not
  affect the LLM call's return value or raise out of `agent_loop.py`.
- No test sends real data to a live Langfuse instance or a real LLM
  provider; `NoopSink`/fakes are used throughout, consistent with the rest
  of this repo's test suite (`backend/tests/` mocks provider/LLM calls
  today — see `test_provider_templates.py`, `test_chat_stream_recovery_e2e.py`).

## 7. Risks / open questions carried into implementation planning

- Exact Langfuse version to pin, and whether the current PostgreSQL/Redis
  already running in `docker-compose.yml` can host Langfuse's dedicated
  database/cache or whether fully separate containers are required —
  resolved with a compatibility check during planning, not this spec.
- Where Langfuse's own object storage bucket lives relative to the existing
  MinIO instance used elsewhere in the repo (share vs. dedicate a bucket).
- Exact set of PII patterns beyond email/phone (the redaction scope is
  fixed in this spec: system/user/assistant content, tool args/results,
  errors, metadata — the pattern list itself is an implementation detail
  refined against `app/core/guardrails/secrets.py`).
- Whether embedding/reranking calls (§ instrumentation scope, confirmed by
  the user as in-scope) go through `LLMDriver` today or need a small
  parallel wrapper — resolved by checking the current embedding call sites
  during implementation planning.
