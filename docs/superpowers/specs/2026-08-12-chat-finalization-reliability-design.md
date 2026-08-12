# Chat Finalization Reliability Design

**Date:** 2026-08-12  
**Scope:** Chat runs that finish after tool execution without a visible assistant response.

## Context and confirmed failure

Run `e67bab02-604a-4919-8517-6bb62e4d064b` completed a successful email delegation and produced the tool result `Hôm nay không có email nào được tìm thấy.`. The root Gemini call then emitted no content and reported `output_tokens=0`. The backend emitted `message_done` with an empty `content`, marked the task `succeeded`, and persisted an assistant message whose content length was zero. The frontend correctly displayed only the run metadata (`4.7s`, `1 tool`) because there was no response text to render.

The earlier Gemini HTTP 400 issue caused by OpenAI-only `additionalProperties` has already been fixed by the Gemini-specific schema normalizer. This design addresses the remaining finalization reliability problem without changing the selected-model persistence work.

## Goals

- Never complete a successful chat run with an empty assistant response.
- Preserve tool side-effect safety: finalization recovery must not execute a tool twice.
- Keep provider-specific protocol conversion at the provider boundary.
- Give the user a deterministic response when a tool succeeded but the provider final answer is empty.
- Make failures and fallback usage observable and testable.
- Keep the frontend from rendering a blank assistant bubble even if an old or malformed run reaches it.

## Non-goals

- No automatic replay of arbitrary failed chat runs.
- No global mutation of OpenAI or Anthropic tool schemas.
- No new database migration for the first implementation.
- No unbounded retries or provider failover during a single chat turn.
- No deletion of existing messages, tasks, approvals, sessions, or volumes.

## Proposed architecture

### 1. Correct Gemini function-response protocol

When the agent appends a tool result to the in-memory provider conversation, the message must retain both the provider tool-call id and the actual function name. The Gemini adapter must serialize `functionResponse.name` using the actual function name, not the tool-call id. OpenAI-compatible and Anthropic serialization remains unchanged.

The agent loop will add `name` to its internal tool-result message where needed. The Gemini adapter will use `message.name` and only use a safe fallback for legacy messages. This prevents a malformed follow-up request after a tool call and does not re-execute the tool.

### 2. Bounded finalization retry

After a tool iteration completes, if the next provider turn returns no content, no reasoning, and no tool calls, the agent loop performs at most one finalization retry.

The retry is a final-answer-only request:

- reuse the exact conversation including the completed tool result;
- send no tool schemas (`tools=None`);
- do not allow tool choice or execute any tool;
- use the same selected model and provider;
- emit a structured internal/observable retry event;
- respect the existing provider timeout and run wall-clock budget.

If the retry returns non-empty content, the normal `message_done` path persists it and marks the task succeeded. If it is also empty, continue to deterministic fallback or failure handling below. The retry counter is local to the current run and cannot loop across iterations.

### 3. Deterministic fallback

If at least one tool result is successful and both the original finalization and the bounded retry are empty, construct a non-empty answer from the most recent successful tool result. The fallback must be deterministic and must not claim facts beyond the tool output. The initial form is explicit and safe:

> Kết quả từ công cụ: `<sanitized tool result>`

The fallback result is subject to the existing secret/PII redaction path and a bounded display length. Its message metadata records `finalization: "tool_result_fallback"`, while the regular tool audit record remains unchanged. The run can be marked `succeeded` because the requested operation completed and the user received the authoritative tool result.

If no successful tool result exists, the run must not be marked succeeded with empty content. It emits an error/incomplete outcome with a user-visible message instructing the user to retry. No synthetic factual answer is created.

### 4. Frontend defense-in-depth

The SSE reducer will treat an empty `message_done` as an explicit incomplete response rather than allowing a blank assistant bubble with only metadata. For a legacy or malformed run, it will render a visible status/error message and retain the tool cards. The backend remains the source of truth; this guard only protects the UI from old data or future regressions.

The persisted-message synchronization must not replace a visible fallback/error state with a blank assistant record. A non-empty persisted assistant message remains authoritative.

## Data flow

1. Provider emits a tool call.
2. Agent executes it exactly once and appends an internal assistant tool-call message plus a named tool-result message.
3. Provider receives the correctly serialized tool response and attempts finalization.
4. If content is non-empty, persist and emit the normal `message_done`.
5. If content is empty and no tool calls are returned, perform one no-tools finalization retry.
6. If retry succeeds, persist and emit the normal final response with retry metadata.
7. If retry is empty and a successful tool result exists, create the deterministic fallback, persist it, emit `message_done`, and mark fallback metadata.
8. If no successful result exists, emit a terminal error/incomplete event and mark the task accordingly.
9. The frontend renders either the final content/fallback or a visible retryable error; never a blank successful assistant response.

## Error handling and safety

- Tool execution and finalization are separate phases. Finalization retry cannot invoke tools.
- Existing cancellation, approval, budget, and wall-clock checks remain in force.
- Provider errors during the retry follow the existing error path, then use fallback only when a successful tool result is available.
- Tool output is treated as untrusted content and passes through existing redaction before persistence/display.
- No credentials, raw provider API keys, or sensitive request headers are written to events or logs.
- Observability records whether the response was direct, retry-generated, fallback-generated, or incomplete, without recording secrets.

## Testing strategy

Backend tests:

- Gemini serializes a tool result with the function name, not the tool-call id.
- Internal tool-result messages preserve the function name.
- An empty provider final response triggers exactly one no-tools retry.
- A successful retry produces normal assistant content and does not execute a tool twice.
- An empty retry with a successful tool result produces deterministic non-empty fallback content and success metadata.
- Empty finalization with no successful tool result produces a terminal error/incomplete result, never a successful empty message.
- Existing model persistence, approval resume, delegation, and provider-schema tests continue to pass.

Frontend tests:

- An empty `message_done` does not render a blank metadata-only assistant message.
- A visible fallback/error state is shown for legacy empty assistant messages.
- Normal streamed content, tool cards, approvals, and persisted-message synchronization remain unchanged.

Runtime smoke tests:

- Run an email query through `email-intelligence` with Gemini and verify a visible response after the tool call.
- Verify the provider request with the tool result no longer returns a malformed/empty final turn.
- Verify the selected model remains the same through the root run and delegated child run.

## Rollout and observability

Ship the backend protocol/finalization changes and frontend guard together. Monitor counts for provider errors, finalization retries, fallback responses, and incomplete runs. A fallback is preferable to a blank success, but an increasing fallback rate indicates provider or prompt/protocol degradation and should trigger investigation rather than masking the issue indefinitely.
