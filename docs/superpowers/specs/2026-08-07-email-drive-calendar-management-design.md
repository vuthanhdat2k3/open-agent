# Email, Drive, and Calendar Agent Management

## Goal

Expand the connected-account agents so they can manage email, Drive files, and calendar events through explicit tools with inline approval for every mutating operation.

## Scope

Email tools: search, get, create draft, send, mark read/unread, star/unstar, archive, trash, restore, list labels, apply/remove labels, reply, and forward.

Drive and calendar follow the same contract: read-only operations run immediately; create, update, move, trash/delete, and event mutations require approval. Destructive file and calendar operations are reversible where the provider supports it.

## Safety contract

- OAuth scopes must cover only the enabled provider operations.
- Every mutating tool remains `requires_approval=True`.
- Approval cards contain only the action and sanitized arguments; no free-form reason is required.
- Gmail delete means moving a message to Trash, never permanent deletion by default.
- Send and delivery operations require an idempotency key.
- Provider errors are normalized into tool results and never bypass approval.

## Architecture

Each provider exposes a typed method, the customer-intelligence MCP server maps it to the provider API, and the agent tool registry exposes a bounded JSON schema. The existing inline approval resume path executes the approved tool exactly once and resumes the conversation. Provider calls are covered by MCP stubs and end-to-end Playwright checks.

## Verification

- Compile and type checks.
- Contract tests for every tool schema and provider operation using the existing MCP stub.
- Playwright flow for representative read, write, approval, rejection, and idempotent retry cases across email, Drive, and Calendar.
