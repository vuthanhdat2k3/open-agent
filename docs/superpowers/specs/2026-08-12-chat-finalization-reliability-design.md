# Chat Finalization Reliability Design

- **Date:** 2026-08-12
- **Revision:** 2 (self-review corrections)
- **Scope:** Chat runs that finish after tool execution without a visible assistant response.

## Context and confirmed failure

Run `e67bab02-604a-4919-8517-6bb62e4d064b` completed a successful email delegation and produced the tool result `Hôm nay không có email nào được tìm thấy.`. The root Gemini call then emitted no content and reported `output_tokens=0`. The backend emitted `message_done` with an empty `content`, marked the task `succeeded`, and persisted an assistant message whose content length was zero.

Verified mechanism for the blank bubble in the UI: `chat-message-item.tsx` returns `null` only when `!m.content && !m.meta?.reasoning && m.meta?.cost_usd == null`. The failing run persisted `cost_usd = 0.0`, which is not `null`, so the component skipped the content block and rendered the metadata badges alone (`4.7s`, `$0.00000`, `1 tool`). The frontend did not lose the answer; there was no answer to render.

Verified protocol defect (root-cause candidate for the empty finalization): `gemini_driver.py` serializes `functionResponse.name` as `message.get("name", message.get("tool_call_id", "tool"))`, but `agent_loop.py` appends tool results as `{"role": "tool", "tool_call_id": ..., "content": ...}` with no `name`. `GeminiDriver._response` mints ids of the form `<function>-<index>-<uuid8>`, so Gemini received `delegate_to_email_intelligence-0-723bc686` as the function name — a name it never declared. The event log for the failing run shows exactly that id at `seq 2`.

The earlier Gemini HTTP 400 caused by OpenAI-only `additionalProperties` is already fixed by the Gemini schema normalizer. This design addresses the remaining finalization problem and does not alter the selected-model persistence work.

## Goals

- Never complete a successful chat run with an empty assistant response.
- Preserve tool side-effect safety: finalization recovery must never execute a tool twice.
- Keep provider-specific protocol conversion at the provider boundary.
- Give the user a deterministic answer when a tool succeeded but the provider final answer is empty.
- Keep token usage, cost, and quota accounting accurate when an extra provider call happens.
- Make direct / retry / fallback / incomplete outcomes observable and testable.
- Prevent the UI from rendering a blank assistant bubble for legacy or malformed runs.

## Non-goals

- No automatic replay of arbitrary failed chat runs.
- No global mutation of OpenAI or Anthropic tool schemas.
- No new database migration; fallback state rides in existing `Message.meta`.
- No unbounded retries, no provider failover inside one chat turn.
- No change to the existing `retry` / `self_correct` events, which mean "a tool failed and the model is correcting", not "finalization was empty".
- No deletion of existing messages, sessions, tasks, approvals, or volumes.

## Proposed architecture

### 1. Correct the Gemini function-response protocol

`agent_loop.py` will include the function name on every tool-result message it appends to the provider conversation (main tool loop, direct approval resume, and delegated approval resume). `GeminiDriver._payload` will then serialize `functionResponse.name` from that name; the existing `tool_call_id` fallback stays only for legacy messages. OpenAI-compatible and Anthropic serialization are unchanged, since both key off `tool_call_id` by design.

This is a protocol correction, not a retry: it does not re-execute the tool.

### 2. Bounded finalization retry

Inside the final-answer branch of `_agent_stream` (the path taken when an iteration produced no tool calls), if the provider turn yielded no content, no reasoning, and no tool calls, perform at most one finalization retry per run, guarded by a per-run boolean.

Retry rules:

- Reuse the same conversation, including the completed tool result.
- Call the provider with `tools=None` and pass no `tool_choice`, so the orchestrator's forced-tool-choice path cannot re-trigger a delegation.
- Use the same selected model and provider as the run.
- The retry is not a loop iteration: it does not consume `agent.max_iterations`.
- Skip the retry and go straight to fallback if the run's wall-clock budget is already exhausted.
- Record the attempt via `structlog` and a metric; do not emit a new SSE event type.

If the retry returns non-empty content, the normal `message_done` path persists it. If it is also empty, fall through to section 3.

### 3. Usage and cost accounting across attempts

The final block currently derives `in_tok` / `out_tok` from the last provider call's `stream_usage`. With a retry there are two provider calls, so token counts must be accumulated across the finalization attempts before computing cost, `usage`, the persisted `Message.meta`, and the `UsageEvent` row. `estimated` is `True` if any counted attempt reported estimated usage. This keeps `agent_run_cost_usd_total`, the monthly-cost cache, and quota enforcement honest.

### 4. Deterministic fallback

If the original finalization and the bounded retry are both empty, and the current turn produced at least one successful tool result (`_is_tool_failure` is false), the answer becomes that last successful tool result, used verbatim.

The fallback content carries no locale-specific prefix. The backend is multi-tenant and multi-language, so injecting a hardcoded Vietnamese or English sentence would be wrong for other organizations; the tool result is already the authoritative, user-facing text. Labelling belongs to the UI.

The fallback text passes through the existing `scan_and_redact` path and is capped at a bounded length. `Message.meta` records `finalization: "tool_result_fallback"`; the tool audit rows are unchanged. The task is marked `succeeded`, because the requested operation completed and the user received the authoritative result.

### 5. Incomplete path when there is no usable tool result

If finalization is empty and no successful tool result exists, the run must not be marked `succeeded` with empty content. Instead:

- Do not persist an empty assistant message.
- Emit a terminal `error` event with a short, retryable reason.
- Mark the task `failed` via `_finish_task`, which does not delete the trailing user turn. The deleting helper `fail_chat_run` must not be used here: the user's message stays in the transcript so they can retry without retyping.
- Invent no factual answer.

### 6. Applicability across depths

The retry, fallback, and incomplete rules live in `_agent_stream`, so they apply to the root chat run and to delegated sub-agents alike. A sub-agent that would otherwise return an empty string to its parent instead returns its tool result or an explicit error. The durable event recorder remains depth-0 only; no change there.

### 7. Frontend defense-in-depth

The SSE reducer treats an empty `message_done` as an incomplete response rather than allowing a metadata-only assistant bubble, and the assistant renderer stops treating a non-null `cost_usd` as sufficient reason to render an empty message. Both show a visible, retryable status instead. UI strings follow the existing chat UI, which is English: `No answer was generated. Please try again.`

Persisted-message synchronization must not replace a visible fallback or error state with a blank assistant record; a non-empty persisted assistant message stays authoritative.

## Data flow

1. Provider emits a tool call.
2. Agent executes it exactly once, then appends an assistant tool-call message and a tool-result message carrying the function name.
3. Provider receives the correctly serialized tool response and attempts finalization.
4. Non-empty content: persist and emit the normal `message_done`.
5. Empty content with no tool calls: perform one no-tools finalization retry, unless the wall-clock budget is exhausted.
6. Retry non-empty: persist and emit the final response, with accumulated usage and `finalization: "retry"`.
7. Retry empty and a successful tool result exists: emit and persist the deterministic fallback with `finalization: "tool_result_fallback"`.
8. No successful tool result: emit terminal `error`, mark the task failed, keep the user message, persist no assistant message.
9. Frontend renders content, fallback, or a retryable error — never a blank successful assistant response.

## Error handling and safety

- Tool execution and finalization are separate phases; the retry cannot invoke tools.
- Cancellation, approval, risk-tier, budget, and wall-clock checks stay in force.
- A provider exception during the retry follows the existing error path, then uses fallback only when a successful tool result exists.
- Tool output is untrusted input and passes through the existing redaction before persistence and display.
- No credentials, API keys, or request headers are written to events, logs, or metrics.

## Observability

Add one bounded counter following the existing naming convention in `app/core/observability/metrics.py`:

```text
chat_finalization_total{outcome="direct|retry|tool_result_fallback|incomplete"}
```

`outcome` is the only label, so cardinality stays fixed. No org, session, or run id is used as a label. `structlog` records the same outcome alongside the existing `chat_latency_phase` events for per-run debugging.

## Testing strategy

Backend:

- Gemini payload serializes a tool result with the declared function name, not the tool-call id.
- Tool-result messages appended by the agent loop carry the function name in all three call sites.
- An empty finalization triggers exactly one no-tools retry, with no `tool_choice` and no second tool execution.
- A successful retry yields normal content and accumulated token usage across both attempts.
- An empty retry with a successful tool result yields non-empty fallback content, `finalization: "tool_result_fallback"`, and a `succeeded` task.
- Empty finalization with no successful tool result yields a terminal error, a failed task, no persisted assistant message, and a retained trailing user message.
- A delegated sub-agent with empty finalization returns its tool result rather than an empty string.
- Existing model-persistence, approval-resume, delegation, and Gemini-schema tests still pass.

Frontend:

- An empty `message_done` renders a retryable status, not a metadata-only bubble.
- A legacy persisted empty assistant message with `cost_usd = 0.0` no longer renders as a blank bubble.
- Normal streaming, tool cards, approvals, and persisted-message sync are unchanged.

Runtime smoke:

- An email query through `email-intelligence` on Gemini shows a visible answer after the tool call.
- The follow-up provider request carrying the tool result no longer produces an empty final turn.
- The selected model stays identical across the root run and the delegated child run.

## Rollout

Ship the protocol fix, finalization handling, and frontend guard together. Watch `chat_finalization_total`: fallback is better than a blank success, but a rising fallback or incomplete rate means provider or protocol degradation and must be investigated rather than masked.
