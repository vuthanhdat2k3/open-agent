# LLM Observability (Langfuse) — Implementation Plan

Date: 2026-08-11
Design: `docs/superpowers/specs/2026-08-11-llm-observability-design.md`
Branch: `feat/llm-observability-langfuse`

## Phase 0 — Baseline and deployment decisions

1. Confirm the pinned Langfuse server/worker release and Python SDK release from
   the official compatibility matrix. Pin exact image tags/digests and exact
   `langfuse` package version; never use `latest` or an open dependency range.
2. Add an opt-in Langfuse Compose profile/override that keeps OpenAgent's
   existing API/frontend ports unchanged. Use the official Langfuse v4
   architecture: web + worker, dedicated Postgres database, ClickHouse,
   Redis/Valkey, and persistent object storage. Keep Langfuse Postgres schema
   separate from OpenAgent's Alembic database.
3. Keep all Langfuse services behind internal Docker networking except the
   Langfuse UI/API port. Put credentials, encryption key, salt, project keys,
   and storage credentials in `.env.example`/runtime secrets, never source.
4. Document startup, health checks, backup/restore of Langfuse Postgres,
   ClickHouse and object storage, plus trace retention/TTL. Validate
   `docker compose config` and service health before code integration.

## Phase 1 — Provider-neutral contract and redaction

1. Add `backend/app/core/observability/llm_trace.py` containing:
   - `TraceContext` with independent `trace_id`/`session_id` and resolved
     content policy.
   - `GenerationRecord` and `ToolObservation` dataclasses with no Langfuse
     imports.
   - `ObservationHandle` protocol with idempotent
     `finish_success/error/cancelled`.
   - `ObservabilitySink` protocol and a safe `NoopSink`.
   - `ObservabilityContext` for parent context, generation/tool starts and
     redacted emission.
2. Add `backend/app/core/observability/redaction.py`:
   - deep-copy/deep-walk strings, dicts, lists and provider message shapes;
   - reuse `scan_and_redact` and extend only the missing secret/PII patterns;
   - redact exception text and metadata values too;
   - never mutate runtime messages;
   - fail closed on content if sanitization itself fails;
   - report redaction count and truncation metadata.
3. Add config for global capture/sampling/enabled flags with secure defaults.
   Resolve policy with global → org/agent → request precedence; lower levels
   can only disable content capture, never enable it above a deny.
4. Add Prometheus counters for emitted, failed, redacted and dropped
   observability events. Unit-test contract idempotency, deep redaction,
   non-mutation, and policy precedence.

## Phase 2 — Instrument all real LLM generations

1. Add `ObservableLLMDriver` wrapping any existing `LLMDriver`; preserve the
   existing stream/complete event contract and return values exactly.
2. Update `build_driver()` to wrap only when a `TraceContext` is supplied.
   Provider discovery/test/health paths must build raw drivers with no context.
3. Build a trace context once per chat/agent/workflow run using `root_run_id`
   as trace id and the independent chat `session_id`.
4. Thread the neutral context into agent loop, workflow generation, compactor,
   memory summarization, sub-agent calls, retry/fallback attempts, and any
   embedding/reranking call sites found during implementation.
5. Instrument each stream as one generation: aggregate content/reasoning/tool
   calls/usage, finish exactly once on success/error/cancellation, record
   monotonic latency, and preserve exception semantics.
6. Add neutral tool hooks at agent and workflow tool execution boundaries.
   Record arguments at start and redacted result/status/error at finish.
7. Add tests for one-generation-per-stream, errors, cancellations, retries,
   fallback metadata, tool success/error/denial, and discovery exclusion.

## Phase 3 — Langfuse sink

1. Add a Langfuse adapter as the only module importing the SDK. Map internal
   traces/generations/tool spans to Langfuse v4 observations while preserving
   parent ids and trace/session ids.
2. Use the SDK's async/batched ingestion path. Sink failures are caught,
   rate-limited in logs, counted, and never propagated to LLM callers.
3. Add startup/shutdown lifecycle: initialize only when enabled/configured;
   flush with a bounded timeout on shutdown; close cleanly in API and worker.
4. Add an integration test with a fake Langfuse client/sink and an optional
   opt-in local Langfuse smoke test that sends no real user/provider data.

## Phase 4 — Debug links and operational controls

1. Persist/return `trace_id` in task/run progress or debug response without
   duplicating prompt content in OpenAgent DB.
2. Add a trace URL helper/config so the debug UI can link to Langfuse; do not
   embed Langfuse UI in v1.
3. Document global/org/agent/request capture controls, sampling, redaction,
   retention and backup operations.
4. Add alerts/metrics for sink failures, queue drops, redaction failures and
   generation latency.

## Validation gates

- Unit tests for redaction, contract lifecycle, policy precedence, driver
  wrapper and tool hooks.
- Existing targeted provider/tool/recovery tests remain green.
- Full backend pytest, Ruff, frontend typecheck/lint/build.
- `docker compose config` and Langfuse profile startup/health smoke test.
- A mocked end-to-end Agent run verifies the full hierarchy and confirms raw
  secret values never reach the sink.
- No tests call a real LLM or send repository/user data to external services.
