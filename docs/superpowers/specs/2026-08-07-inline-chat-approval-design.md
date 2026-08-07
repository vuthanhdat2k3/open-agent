# Inline Chat Approval and Durable Resume

## Goal

Allow users to approve or reject a tool request directly inside the chat and
ensure an approved chat run resumes exactly once instead of remaining in
`waiting_approval`.

## Current problem

The agent loop creates an `ApprovalRequest`, records an `approval_required`
event, marks the root `Task` as `waiting_approval`, and returns. The generic
approval endpoint only changes the approval row's status. It does not enqueue
or resume the task. The chat UI also renders only a passive waiting indicator,
so the user must navigate away to decide the request.

## Design

### Durable state and API

Keep `ApprovalRequest` as the source of truth. Agent approvals must reference
the durable chat run in `run_id` (not only the session). The decision endpoint
will:

1. Lock/read the approval and verify organization and permission scope.
2. Return the existing decision for an already-decided request (idempotent
   client retries), without scheduling another execution.
3. For a pending request, write `approved` or `rejected`, audit the action,
   and schedule a resume/rejection job for the associated chat run.

The resume operation is guarded by the approval id and run id. It must claim
the request/run transition before executing, so concurrent clicks, duplicate
HTTP requests, or worker retries cannot execute the approved tool twice.

### Resume behavior

The worker resumes the chat run through the existing durable queue and event
log. It reloads the session conversation, approval decision, and task state;
then continues the agent turn with the approved tool call represented in the
conversation. The tool call is recorded with the approval id as its
idempotency reference. A rejected request emits a terminal rejection event and
finishes the run with an explicit rejected result.

Existing side-effect safeguards remain authoritative. No approval resume may
skip risk-tier checks, permission checks, payload validation, or tool-level
idempotency. Expired requests cannot be approved and are terminal.

### Event contract

`approval_required` contains:

- `approval_id`
- `run_id`
- `tool_name`
- sanitized `args_snapshot` for display

The event is durable and replayable. A terminal `approval_rejected` event is
added for rejection. Normal resumed execution continues through the existing
tool and `message_done` events. Event payloads must not expose credentials or
secret environment values.

### Chat UI

Replace the passive “Waiting for approval” row with an inline approval card.
The card shows the requested tool, sanitized arguments, and two accessible
buttons: `Approve` and `Reject`.

While deciding, both buttons are disabled. On success, the card becomes a
read-only `Approved` or `Rejected` state. The client then keeps/reattaches the
run event stream so the approved run can show tool progress and its final
answer. Reloading the page reconstructs the same card from durable events and
the approval query.

The existing Approvals page remains available and uses the same decision API;
it is not a second approval implementation.

## Failure handling

- Decision request failure re-enables the buttons and shows a non-destructive
  error.
- A stale or already-decided request displays the server's authoritative
  status and does not retry execution.
- Queue failure leaves an auditable approved decision and a retryable resume
  job; it must not silently reset the approval to pending.
- Worker retry/lease recovery is bounded and uses the existing orphan/run
  recovery mechanisms.

## Verification

Add coverage for:

- event payload containing the approval details;
- inline approve and reject API calls;
- approve schedules/resumes exactly one chat run;
- duplicate decision requests do not execute twice;
- reject produces a terminal run state;
- reload/replay renders the approval card;
- queue failure and worker retry remain recoverable;
- frontend type-check/build.

## Scope deliberately excluded

No reason input, bulk approval, new approval page, notification system, or
new queue technology. The implementation reuses the current task, event log,
Redis/ARQ queue, audit, and permission infrastructure.
