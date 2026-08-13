# Personal Email Intelligence Frontend — Production Design Specification

> Status: approved for implementation
> Date: 2026-08-13
> Target: Docker Compose/VPS, fewer than 100 users
> Supported identities: Google Workspace and personal Gmail
> Related backend specification: `docs/superpowers/specs/2026-08-13-personal-email-intelligence-automation-design.md`

## 1. Purpose

This document specifies the production frontend for Personal Email Intelligence. The feature receives Gmail changes asynchronously, classifies and routes email, creates customer research briefings, proposes calendar actions, asks for approval before external side effects, and exposes operational state to authorized administrators.

The frontend has two role-separated workspaces:

1. **User Workspace** for personal email intelligence, research, approvals, automation rules, and personal Google connections.
2. **Admin Operations** for aggregate health, scheduler state, queue/dead-letter inspection, manual reviews, and cross-lifecycle traces.

Frontend visibility is not an authorization boundary. The server computes capabilities for every resource and re-authorizes every command.

## 2. Scope

### 2.1 In scope

- Smart Inbox for normalized and classified email.
- Shared email/case detail surface.
- Research case list, detail, report, provenance, retry, cancel, and manual research.
- Approval list and detail with risk, approval mode, expiry, proposal version, and decision actions.
- Trusted automation rules for calendar auto-create only.
- Gmail, Google Calendar, and Google Drive connection management.
- User-owned schedules.
- Admin overview, connection health, scheduler state, canonical queue/dead-letter state, manual reviews, and trace explorer.
- Canonical REST reads with SSE invalidation and polling fallback.
- Server-computed capabilities, version preconditions, HTTP idempotency, and stable error behavior.
- Responsive desktop-first UI, WCAG 2.2 AA target, security-safe rendering, test coverage, and staged rollout.

### 2.2 Explicitly out of scope for the first production release

- Trusted-rule automatic email sending.
- Trusted-rule automatic Knowledge Base writes.
- Editing raw Redis queue payloads.
- Direct Redis queue inspection as business truth.
- A Grafana replacement inside the application.
- Rendering unsanitized HTML email.
- Loading remote email images by default.
- Wildcard trusted rules.
- Public-email-domain trusted rules.
- Force-executing a side effect from Admin Operations.
- Reconstructing canonical application state from SSE events.
- Frontend access to executor idempotency keys, OAuth tokens, MinIO object keys, or raw provider payloads.

## 3. Product principles and invariants

### 3.1 Authorization and capabilities

- The frontend never infers executable permission from `role`, ownership fields, status, or route location.
- Every mutation-capable resource returns server-computed `capabilities`.
- Missing capability data fails closed: executable actions are not rendered.
- A route-level capability controls navigation visibility; resource-level capabilities control actions.
- The backend rechecks organization, owner, policy, expiry, payload hash, proposal version, and current state for every command.

### 3.2 Canonical state

- REST responses are canonical.
- SSE announces only that a resource changed.
- After an SSE event, the client invalidates and refetches the targeted REST query.
- SSE reconnect never replays business state into the client store.
- PostgreSQL-backed API responses, not Redis transport state, determine UI state.

### 3.3 Side-effect integrity

- Approve, reject, cancel, retry, resolve, and trusted-rule mutations are not optimistic.
- Mark-read may be optimistic because it is reversible and has no external side effect.
- A `202 Accepted` response means queued, not completed.
- A timeout after a command produces `VERIFYING_OUTCOME`, not success or automatic resubmission.
- A stale proposal must be reviewed again before a new decision.

### 3.4 Time and urgency

- Relative countdowns derive from absolute `expires_at` and response `meta.server_time`.
- The UI does not trust the workstation clock for approval or SLA decisions.
- The server-time utility records `meta.server_time` together with `performance.now()` and advances from monotonic elapsed time; it does not repeatedly subtract `Date.now()` from the server timestamp.
- A later canonical response corrects the server-time baseline and clock drift.
- Countdown displays refresh every 30 seconds.
- Reaching zero disables the action and triggers a canonical refetch.
- Navigation badges separate ordinary counts from urgent or SLA-breached counts.

### 3.5 Untrusted content

- Email content, attachment metadata, web content, report excerpts, and provider error text are untrusted data.
- Untrusted content never becomes HTML instructions, navigation commands, or action authorization.
- Guard flags are security context; they do not automatically delete every flagged email.

## 4. Information architecture

### 4.1 User Workspace routes

| Route | Label | Purpose |
|---|---|---|
| `/email-intelligence` | Smart Inbox | Classified email, routing outcome, unread state, linked case/proposal |
| `/customer-intelligence` | Research Cases | Company research cases and briefing reports |
| `/approvals` | My Approvals | Pending personal actions and existing agent/tool approvals |
| `/email-intelligence/rules` | Automation Rules | Trusted calendar auto-create rules |
| `/integrations` | Connections | Gmail, Calendar, and Drive OAuth connections and health |

### 4.2 Admin Operations routes

| Route | Label | Purpose |
|---|---|---|
| `/admin/email-intelligence` | Overview | Operational signals that require attention |
| `/admin/email-intelligence/connections` | Connections Health | Aggregate watch, sync, scope, and backoff state |
| `/admin/email-intelligence/schedulers` | Schedulers | Canonical occurrences, leases, failures, and next run |
| `/admin/email-intelligence/queue` | Queue & Dead-letter | PostgreSQL-backed event and attempt state |
| `/admin/email-intelligence/reviews` | Reviews | Ambiguous side effects awaiting manual resolution |
| `/admin/email-intelligence/traces` | Trace Explorer | Sanitized lifecycle timeline by correlation/resource ID |

### 4.3 Navigation behavior

- User Workspace navigation is shown when `can_access_user_workspace=true`.
- Admin Operations navigation is shown when `can_access_admin_operations=true`.
- Navigation does not inspect membership role to make the decision.
- My Approvals shows ordinary pending count and a separate urgent count.
- Reviews shows open count and a red due-soon/breached count.
- A route visited after capability removal returns a forbidden state, refreshes navigation summary, and redirects to the nearest authorized route.

## 5. Frontend technical architecture

### 5.1 Existing stack to reuse

- Next.js 15 App Router.
- React 19.
- TypeScript.
- TanStack Query for canonical server state.
- React Hook Form and Zod for commands and forms.
- Existing Radix-based UI components.
- Existing `streamSSEGet`/SSE patterns in `frontend/lib/api.ts`.
- Existing toast, loading, error, and confirmation primitives.

No additional global state library is required for canonical business data. Zustand may remain for existing local application state but must not duplicate REST resources.

### 5.2 Required frontend modules

```text
frontend/
  app/
    email-intelligence/
      page.tsx
      rules/page.tsx
    customer-intelligence/page.tsx
    approvals/page.tsx
    admin/email-intelligence/
      page.tsx
      connections/page.tsx
      schedulers/page.tsx
      queue/page.tsx
      reviews/page.tsx
      traces/page.tsx
  components/email-intelligence/
    smart-inbox.tsx
    intelligence-detail.tsx
    guard-summary.tsx
    routing-summary.tsx
    action-timeline.tsx
    approval-list.tsx
    approval-detail.tsx
    automation-rule-form.tsx
    connection-health.tsx
    admin-overview.tsx
    manual-review-detail.tsx
    trace-timeline.tsx
  hooks/email-intelligence.ts
  lib/email-intelligence/
    api.ts
    schemas.ts
    query-keys.ts
    capabilities.ts
    reason-registry.ts
    server-time.ts
    idempotency.ts
    view-models.ts
```

Files may be split further when a component has a distinct responsibility. The implementation must not create one component per backend lifecycle merely to mirror internal state names.

### 5.3 Query keys

Every query key includes active organization ID:

```ts
["email-intelligence", orgId, "navigation-summary"]
["email-intelligence", orgId, "emails", filters]
["email-intelligence", orgId, "email", emailId]
["customer-intelligence", orgId, "cases", filters]
["customer-intelligence", orgId, "case", caseId]
["email-intelligence", orgId, "approvals", filters]
["admin-email-intelligence", orgId, "overview"]
```

On signout or organization switch:

1. Abort active email-intelligence requests and streams.
2. Clear affected React Query caches.
3. Clear transient command/idempotency state.
4. Load the new organization capability summary before rendering protected data.

## 6. Common API contracts

### 6.1 List envelope

```json
{
  "items": [],
  "page": {
    "next_cursor": null,
    "has_more": false
  },
  "filtered_counts": {
    "total": 0,
    "urgent": 0
  },
  "meta": {
    "server_time": "2026-08-13T05:00:00Z",
    "correlation_id": "uuid",
    "reason_registry_version": "2026-08-13.1"
  }
}
```

`filtered_counts` describes only the current filtered result. It must never drive global navigation badges.

### 6.2 Navigation summary

`GET /api/email-intelligence/navigation-summary`

```json
{
  "user_workspace": {
    "inbox": {"unread": 8, "urgent": 1},
    "research_cases": {"active": 3, "failed": 1},
    "approvals": {"pending": 4, "urgent": 2}
  },
  "admin_operations": {
    "manual_reviews": {"open": 5, "urgent": 2},
    "dead_letters": {"total": 3, "urgent": 1},
    "connections": {"unhealthy": 2}
  },
  "capabilities": {
    "can_access_user_workspace": true,
    "can_access_admin_operations": true
  },
  "meta": {
    "server_time": "2026-08-13T05:00:00Z",
    "reason_registry_version": "2026-08-13.1"
  }
}
```

Refresh on application bootstrap, tab visibility return, relevant SSE event, successful mutation, and a 60-second visible-tab interval.

### 6.3 Capabilities

Capabilities use booleans plus stable blocked reason codes:

```json
{
  "capabilities": {
    "can_view_detail": true,
    "can_approve": false,
    "can_reject": true,
    "can_cancel": false,
    "blocked_reasons": {
      "approve": "approval.expired",
      "cancel": "capability.only_proposal_owner_can_cancel"
    }
  }
}
```

Rules:

- Unknown or missing executable capability is treated as false.
- `blocked_reasons` is display context, not authorization.
- The UI maps reason codes to localized copy and severity.
- A capability may change between read and command; the command result is authoritative.

### 6.4 Reason-code registry

All guard, routing, risk, approval, execution, connection, scheduler, and capability reason codes belong to one versioned registry.

Namespaces:

```text
guard.*
routing.*
risk.*
capability.*
approval.*
execution.*
connection.*
scheduler.*
```

The frontend owns one presentation map per supported registry version. Unknown codes render a generic localized policy message, preserve the raw code only in safe diagnostic telemetry, and never enable an action.

### 6.5 Stable error envelope

```json
{
  "error": {
    "code": "PROPOSAL_VERSION_CONFLICT",
    "message": "Proposal changed; reload before deciding.",
    "correlation_id": "uuid",
    "retryable": false,
    "field_errors": {}
  }
}
```

Provider payloads, stack traces, decrypted content, and tokens must not appear in errors.

## 7. Data flow and consistency

### 7.1 Read path

```text
Route
  → TanStack Query with organization-scoped key
  → canonical REST resource
  → Zod validation
  → resource adapter/view-model
  → UI component
```

If a mutation-capable response fails Zod validation, action controls fail closed and the UI displays a reloadable contract error with correlation ID.

### 7.2 SSE path

SSE events contain only:

```json
{
  "event": "resource.changed",
  "data": {
    "resource_type": "approval",
    "resource_id": "uuid",
    "version": 4
  }
}
```

The client maps the resource type to query invalidation. It does not merge an SSE payload into canonical detail state.

Behavior:

- Exponential reconnect backoff with jitter, capped at 30 seconds.
- REST polling every 30 seconds while disconnected and tab is visible.
- Refetch canonical REST after reconnect.
- Stop stream and polling while signed out.
- Recreate the stream after organization switch with the new organization context.

### 7.3 Command path

```text
User intent
  → capability-visible control
  → review/confirmation
  → client-generated Idempotency-Key
  → command with expected_version
  → server authorization and state checks
  → canonical command response
  → targeted invalidation
```

The client generates one UUID for one deliberate command. The same UUID is reused only when retrying that command after an ambiguous network outcome.

This HTTP `Idempotency-Key` is independent from the server-generated deterministic `ActionExecution.idempotency_key`. The executor key is never exposed to or supplied by the frontend.

## 8. Shared Intelligence Detail

Smart Inbox and Research Cases use one `SharedIntelligenceDetailVM` and one detail component family.

### 8.1 Normalized view-model

```json
{
  "resource": {
    "type": "email",
    "id": "email-uuid",
    "version": 2,
    "status": "ROUTED"
  },
  "header": {
    "title": "Meeting next week",
    "subtitle": "contact@fpt.com",
    "received_at": "2026-08-13T03:58:00Z"
  },
  "email": {
    "sender": "contact@fpt.com",
    "recipients": ["user@example.com"],
    "body_preview": "Bounded preview",
    "attachment_count": 1
  },
  "guard": {
    "outcome": "RESTRICTED",
    "reason_codes": ["guard.prompt_injection_signal"],
    "scan_status": "COMPLETED",
    "warning": "Content is treated as untrusted data."
  },
  "classification": {
    "label": "CALENDAR",
    "confidence": 0.94,
    "reason_codes": ["routing.meeting_intent"],
    "model_version": "email-classifier-v1"
  },
  "routing": {
    "status": "ROUTED",
    "routes": ["CALENDAR_PROPOSAL"],
    "suppressed_routes": ["CALENDAR_AUTO_CREATE"],
    "reason_codes": ["routing.guard_restricted"]
  },
  "research": {
    "case_id": null,
    "status": null,
    "report_id": null
  },
  "proposals": [
    {
      "id": "proposal-uuid",
      "version": 3,
      "action_type": "calendar_create",
      "status": "AWAITING_APPROVAL"
    }
  ],
  "timeline": [
    {
      "id": "event-uuid",
      "type": "EMAIL_CLASSIFIED",
      "occurred_at": "2026-08-13T03:59:04Z",
      "label": "Classified as calendar email",
      "severity": "INFO"
    }
  ],
  "capabilities": {
    "can_view_full_email": true,
    "can_reprocess": false,
    "can_open_case": false,
    "can_open_proposal": true,
    "blocked_reasons": {
      "reprocess": "capability.processing_already_completed"
    }
  }
}
```

### 8.2 Adapters

- `emailDetailToSharedVM()` transforms email aggregate detail.
- `caseDetailToSharedVM()` transforms research case aggregate detail.
- Adapters validate enums and omit unavailable sections.
- Unknown lifecycle states render as an explicit unsupported-state warning and do not expose action buttons.

### 8.3 Visual sections

1. Header and source identity.
2. Guard status and warnings.
3. Classification confidence and reason.
4. Routing decision and suppressed routes.
5. Linked research/report.
6. Action proposals and proposal versions.
7. Linear action timeline.
8. Sources and meeting matches for research cases.

## 9. Smart Inbox

### 9.1 List

`GET /api/email-intelligence/emails` supports cursor pagination and filters for connection, read status, classification, routing status, guard outcome, and received date.

Each row contains bounded metadata, sender, subject, preview, guard outcome, classification, routing, linked resource IDs, read state, and capabilities. The list does not return full body or attachment bytes.

### 9.2 Defaults

- Spam is excluded from the default view.
- An Ignored filter exposes spam/ignored messages for false-positive review.
- Quarantined/security-risk items remain visible with warning treatment.
- URLs and attachments are not interactive for restricted or quarantined items.
- Selecting a row opens Shared Intelligence Detail.

### 9.3 Notifications and read state

- In-app notifications link to their canonical email, case, or proposal.
- Mark-read is idempotent and may update optimistically.
- On mark-read failure, the client restores previous state and displays a non-destructive error.
- Notification count comes from navigation summary, not the current inbox filter.

## 10. Research Cases

### 10.1 List content

- Company name and domain.
- Trigger type and linked email.
- Case status and confidence.
- Current deterministic workflow stage.
- Report executive summary, source count, warning count, and created time.
- Error category when retry or intervention is possible.
- Server-computed capabilities.

### 10.2 Detail content

- Shared Intelligence Detail.
- Seven canonical report sections.
- Source provenance with publisher, published/retrieved dates, excerpt, and confidence.
- Meeting matches and match confidence.
- Missing-data warnings.
- Report version and linked proposals.
- Timeline and correlation ID.

### 10.3 Commands

| Command | Requirement | Response UI |
|---|---|---|
| Create manual case | Idempotency-Key | Queued, then canonical refetch |
| Cancel | Idempotency-Key and expected version | Canceled only after response |
| Retry | Idempotency-Key and expected version | Queued recovery event |

The frontend must not invent a numeric percentage when the backend only exposes workflow stage.

## 11. My Approvals

### 11.0 Approval sources and ownership

The existing product also has agent/tool approval requests. The page keeps one user-facing “My Approvals” destination but separates sources into clear tabs:

- Email actions backed by versioned Action Proposals.
- Agent and workflow tool requests backed by the existing ApprovalRequest lifecycle.

Each source has a small adapter into shared list presentation fields such as title, risk, expiry, status, and capabilities. Email Action Proposal commands continue to use the versioned proposal endpoints in this specification; the frontend must not pretend the older agent/tool approval lifecycle has proposal-version semantics when it does not.

For a normal user, both list sources must be owner-scoped by the server. An organization-wide pending approval list must never be returned and then filtered in the browser. Admin organization-wide review is exposed only through an explicit server capability and admin scope.

Raw `args_snapshot` is not rendered directly. The API returns or the frontend derives from an approved schema a sanitized review projection for each known tool. Unknown tool payloads fail closed and require a generic safe review surface without executable actions until the server supplies capabilities.

### 11.1 List item

```json
{
  "id": "approval-uuid",
  "proposal_id": "proposal-uuid",
  "proposal_version": 3,
  "action_type": "calendar_create",
  "title": "Create meeting with FPT Software",
  "summary": "14:00–15:00, 2026-08-15",
  "status": "PENDING",
  "risk": {
    "level": "HIGH",
    "reason_codes": ["risk.external_side_effect", "guard.restricted"]
  },
  "approval": {
    "mode": "EXPLICIT",
    "requested_at": "2026-08-13T04:15:00Z",
    "expires_at": "2026-08-13T05:45:00Z"
  },
  "capabilities": {
    "can_view_detail": true,
    "can_approve": true,
    "can_reject": true,
    "can_cancel": false,
    "can_edit": false,
    "blocked_reasons": {
      "cancel": "capability.only_proposal_owner_can_cancel"
    }
  }
}
```

Risk level, approval mode, and countdown are visible in list view.

### 11.2 Detail

Detail includes proposal payload, server-computed payload hash, version, approval scope, risk summary, sanitized origin, version history, timeline, expiry, and capabilities.

The review dialog:

- Places initial focus on review content, not Approve.
- Shows recipient/attendees, time, timezone, content preview, target connection, attachments/links, risk reasons, and expiry.
- Requires current canonical detail before enabling decision controls.
- Does not allow approval after countdown reaches zero.

### 11.3 Decision command

```http
POST /api/actions/proposals/{proposal_id}/decision
Idempotency-Key: client-generated-uuid
Content-Type: application/json
```

```json
{
  "decision": "APPROVE",
  "expected_proposal_version": 3,
  "approval_id": "approval-uuid",
  "reason": "Recipient and time verified"
}
```

- Double-clicking submits once.
- Mutation controls stay disabled while pending or verifying outcome.
- A proposal edit creates a new version and invalidates prior approval.
- Approval never directly causes the UI to claim provider success; execution state is fetched separately.

## 12. Automation Rules

### 12.1 Phase-one action scope

The only trusted-rule action is `CALENDAR_AUTO_CREATE`.

Automatic email send and Knowledge Base write remain explicit-approval-only.

### 12.2 Required rule fields

- Exact sender email or exact organization domain.
- Target calendar connection.
- Minimum classification confidence.
- Maximum events per day.
- Expiry.
- Required guard outcome, fixed to `PASS`.
- Required sender authentication policy.

### 12.3 Deny-by-default validation

Reject or downgrade rules when any condition applies:

- Wildcard match.
- Empty sender or domain.
- Public email domain used as a domain-wide match.
- Missing expiry.
- Unlimited daily cap.
- Confidence below server policy minimum.
- Guard outcome other than `PASS`.
- Attachment or URL scan pending/incomplete.
- Sender authentication not verified and aligned.
- Target connection does not belong to the user or is unhealthy.
- User or organization active-rule quota exceeded.
- User or organization aggregate daily budget exceeded.

An exact sender on a public provider may be configured only when sender authentication satisfies policy. Otherwise the route falls back to explicit approval.

### 12.4 Public-email-domain registry

- Stored in a server-side DB/config registry, not frontend code.
- Versioned independently and returned in policy metadata.
- Updatable through an authorized admin API or operational CLI without application deployment.
- Includes major consumer providers and aliases.
- Frontend displays server validation results and registry version; it does not decide whether a domain is public.

### 12.5 Rule and budget limits

Default server policy:

```text
max_active_rules_per_user = 10
max_active_rules_per_org = 200
max_auto_events_per_user_per_day = 20
max_auto_events_per_org_per_day = 500
```

Values are configurable server policy and never hardcoded as frontend authorization logic.

Budget reservation must be atomic. The backend must use a conditional update, row lock with constraint, or equivalent transaction that prevents concurrent matches from exceeding user or organization caps. Read-then-write application logic is forbidden.

Conceptual SQL behavior:

```sql
UPDATE ci_automation_budgets
SET used = used + 1, updated_at = now()
WHERE scope_id = :scope_id
  AND budget_date = :budget_date
  AND used < budget_limit
RETURNING used;
```

Both user and organization reservations must succeed in one transaction before auto-create dispatch. A failed reservation falls back to explicit approval and records a reason code.

### 12.6 Rule creation flow

1. Select exact sender or exact domain.
2. Select target calendar connection.
3. Set confidence, daily cap, and expiry.
4. Run read-only preview.
5. Review risk and policy summary.
6. Submit with Idempotency-Key.

The preview endpoint returns estimated recent matches, sanitized samples, `would_execute`, blocked reason codes, policy warnings, and policy/registry versions. Preview creates no proposal, execution, or provider side effect.

### 12.7 Rule lifecycle

- Create/update uses Idempotency-Key.
- Update requires expected version and creates a new rule version.
- Disable prevents new dispatch but does not claim an already-executing action was canceled.
- Delete is soft-delete when audit retention requires history.
- Every change records actor, before/after hash, policy version, and timestamp.
- No UI control tests a rule by creating a real calendar event.

## 13. Connections

### 13.1 User view

Each Gmail, Calendar, or Drive connection shows:

- Provider and account label.
- Connection status.
- Credential presence without exposing credential data.
- Required/missing scope status.
- Last sync and last successful operation.
- Gmail watch status and expiry when applicable.
- Health reason codes.
- Capabilities for sync, reauthorize, and disconnect.

### 13.2 Commands

- OAuth connect.
- Reauthorize missing scopes.
- Manual durable sync.
- Disconnect.

Disconnect confirmation states that new watches stop, retained audit/history is not immediately deleted, and pending actions cannot execute through an invalid connection.

### 13.3 Ownership

- Users see and manage only their own connections.
- Admin aggregate views use masked account labels.
- Connection commands still enforce owner/capability server-side.

## 14. Admin Operations

### 14.1 Overview

One aggregate endpoint returns connection health, canonical queue counts, oldest queue age, dead-letter count, manual review SLA counts, scheduler health, capabilities, and server time.

This screen answers “what needs action now” and does not reproduce full Grafana metrics.

### 14.2 Connections Health

Rows contain masked account, owner label, connection ID, watch expiry, last push/sync success, next reconciliation, provider backoff, health reasons, and capabilities.

Tokens, full credentials, and email content are never returned.

### 14.3 Schedulers

Display PostgreSQL-canonical occurrence data:

- Job key and entity type.
- Masked entity label.
- Scheduled time.
- Last started/completed time.
- Next run.
- Lease state.
- Consecutive failure count.
- Provider `next_allowed_at`.
- Capabilities.

Entity-scoped jobs must show their entity identity; a global dispatcher occurrence is not presented as proof that every child entity succeeded.

### 14.4 Queue and dead-letter

- Read Outbox, ProcessedEvent, ActionExecution, and DeliveryAttempt projections from PostgreSQL.
- Do not treat Redis payload as canonical.
- Show sanitized event metadata, attempts, age, failure category, and correlation ID.
- Permit retry only when `can_retry=true`.
- Never allow payload editing or force-execution.

### 14.5 Manual Reviews

Each row shows ambiguity category, action type, masked owner, opened/due timestamps, SLA state, risk, and capabilities.

SLA states:

```text
NORMAL
DUE_SOON
BREACHED
```

Thresholds are server policy. The frontend maps state to presentation.

Resolution detail exposes sanitized evidence and only the four approved outcomes from the backend contract. No outcome transitions directly back to `EXECUTING`; any new attempt requires a new proposal.

### 14.6 Trace Explorer

Search inputs:

- Correlation ID.
- Email ID.
- Case ID.
- Proposal ID.
- Execution ID.

Results form a sanitized linear timeline across notification, ingestion, guard, classification, routing, research, proposal, approval, execution, and attempt events. Raw email body, tokens, attachment bytes, and provider payloads are excluded.

## 15. Error and loading behavior

### 15.1 Query states

Every screen supports:

```text
INITIAL_LOADING
SUCCESS
EMPTY
PARTIAL_ERROR
STALE
RECONNECTING
FATAL_ERROR
```

- Initial load uses structure-matching skeletons.
- Background refetch keeps existing data and shows a subtle updating state.
- One failed widget does not blank the admin dashboard.
- Empty state is shown only after a successful empty response.
- Error state includes a safe correlation ID when provided.

### 15.2 Mutation states

```text
IDLE
SUBMITTING
SUCCEEDED
CONFLICTED
VERIFYING_OUTCOME
FAILED
```

- Network timeout after submit enters `VERIFYING_OUTCOME`.
- The client fetches canonical state before allowing retry.
- Retry uses the original HTTP Idempotency-Key.
- Success notification appears only after a canonical server response.

### 15.3 HTTP mapping

| HTTP status | Meaning | UI behavior |
|---|---|---|
| `403` | Capability/ownership no longer valid | Refetch, remove action, explain permission/state changed |
| `404` | Resource unavailable in current scope | Show unavailable and return to scoped list |
| `409` | State conflict or already resolved | “This request has already been handled”; close command dialog and refetch |
| `412` | Expected version/payload precondition stale | “Content changed”; refetch and require complete review again |
| `422` | Invalid command fields | Preserve form and show field errors |
| `429` | Rate limit | Show retry time; do not auto-submit side effect |
| Retryable `5xx` | Infrastructure failure | Allow retry with same HTTP Idempotency-Key |
| Timeout/no response | Ambiguous API result | Verify canonical state before retry |

## 16. Empty states

| Surface | Message and action |
|---|---|
| Smart Inbox | No processed email; link to Connections |
| Research Cases | No cases; connect Gmail or start manual research |
| My Approvals | No pending approvals |
| Automation Rules | Auto-create disabled by default; explain explicit approval |
| Connections | No Google connection; start OAuth |
| Manual Reviews | No ambiguous execution awaiting review |
| Dead-letter | No event requiring intervention |
| Trace Explorer | Enter a correlation or resource ID |

## 17. Security rendering and privacy

### 17.1 Content rendering

- Render email body as plain text in phase one.
- Never use `dangerouslySetInnerHTML` for email or research content.
- Markdown reports use `react-markdown` with `rehype-sanitize` and no raw HTML.
- `rehype-raw` is forbidden on untrusted email/report content.
- Do not load remote email images by default.
- Permit only validated `https:` and `mailto:` links.
- Restricted/quarantined URLs are non-clickable.
- External links use `rel="noopener noreferrer"`.

### 17.2 Sensitive data handling

- Do not store email body, approval payload, OAuth token, or provider credentials in localStorage.
- Clear organization-scoped caches on signout and organization switch.
- Download attachments only through authorized APIs.
- Never expose MinIO keys.
- Admin lists mask email and identifiers unless detail capability allows more.
- Do not send raw content to frontend telemetry or error reporting.
- Copy-to-clipboard requires an explicit user action.

### 17.3 Browser security

- Maintain a restrictive Content Security Policy compatible with Next.js deployment.
- Disallow framing by untrusted origins.
- Validate redirects against an allowlist.
- OAuth callback pages do not render provider secrets or raw error payloads.
- Authentication/session clearing must remove in-memory and persisted client state.

## 18. Accessibility and responsive behavior

### 18.1 Accessibility target

Target WCAG 2.2 AA for critical flows.

- Keyboard access for lists, filters, dialogs, and actions.
- Focus returns to trigger after dialog close.
- Approval dialog initially focuses review content, not Approve.
- Color is never the only risk/SLA signal.
- Countdown does not announce every 30-second tick.
- Announce only due-soon and expired transitions.
- Mutation results use polite live regions.
- Loading skeletons have accessible labels.
- Respect reduced-motion preference.
- Minimum 44×44 px interactive targets.
- Timeline has a linear reading order.

### 18.2 Responsive layout

- At 1280 px and above: split list/detail view.
- From 768 to 1279 px: list with detail drawer or detail route.
- Below 768 px: single-column stacked rows.
- Admin trace/queue summaries remain readable on mobile; full operational work may require desktop.
- Cursor pagination uses a default page size of 50.
- Do not add virtualization until measured list size or rendering cost requires it.

## 19. Observability

Frontend telemetry is metadata-only and must include organization-safe identifiers:

- Route load success/failure and duration.
- Contract validation failures.
- SSE connection/reconnect/fallback state.
- Mutation status and stable error code.
- Unknown reason-code occurrence and registry version.
- Approval countdown expiry transition.
- Trusted-rule preview rejection reason category.

Never record email body, report text, proposal payload, recipient list, token, or raw provider response.

## 20. Testing strategy

### 20.1 Tooling

Add:

- Vitest.
- React Testing Library.
- jsdom.
- Playwright for critical end-to-end tests.

Avoid broad snapshot suites. Prefer behavior and contract assertions.

### 20.2 Unit tests

- `emailDetailToSharedVM`.
- `caseDetailToSharedVM`.
- Reason registry and unknown-code fallback.
- Countdown based on `meta.server_time`.
- Navigation counts independent from list filters.
- Capability false/missing hides executable action.
- HTTP Idempotency-Key persists across ambiguous retry.
- 409 and 412 produce different states/messages.
- SLA presentation.
- Organization-scoped query keys.
- Trusted-rule policy presentation.

### 20.3 Component tests

- Approval list shows risk, mode, and expiry.
- Expired approval cannot submit.
- Double-click Approve sends one request.
- Shared detail renders restricted content safely.
- Smart Inbox rolls back failed optimistic mark-read.
- Automation Rule rejects wildcard/public-domain domain scope.
- Manual Review omits Resolve when capability false.
- Organization switch does not display stale organization data.
- Unknown server enum fails closed on action surfaces.

### 20.4 End-to-end tests

1. User connects Gmail and sees connection health.
2. Normal email appears in Smart Inbox.
3. Customer email creates a research case and report.
4. Calendar email creates a proposal without creating an event before approval.
5. Approved proposal waits for canonical execution result.
6. Expired approval is disabled.
7. 409 displays already-handled behavior.
8. 412 reloads and requires review again.
9. User cannot access Admin Operations.
10. Admin cannot resolve when `can_resolve=false`.
11. Public-domain domain rule is rejected.
12. Auto-create requires guard pass, confidence, sender authentication, and budget.
13. SSE disconnect falls back to polling and reconnects without duplicate state.
14. Signout and organization switch clear sensitive caches.
15. Email XSS/prompt-injection fixture cannot execute markup or action.
16. Timeout after approval enters verifying state and does not create a second command.

Use fake providers and deterministic fixtures. CI must not call real Gmail, Calendar, Drive, LLM, or production databases.

### 20.5 Backend concurrency tests required by frontend safety

The release must include a concurrent trusted-rule budget test:

- Initialize remaining user and organization budget to one.
- Dispatch at least two matching emails concurrently.
- Assert exactly one atomic reservation succeeds.
- Assert at most one auto-create execution is created.
- Assert the rejected concurrent match falls back to explicit approval with a budget reason code.
- Repeat at both user and organization limits.
- Verify retry/replay does not consume the budget twice for one logical action.

### 20.6 Contract tests

- OpenAPI responses match frontend Zod schemas.
- Missing capabilities fail closed.
- Unknown reason code renders fallback.
- Cross-user/cross-organization reads and commands are denied.
- SSE events carry identifiers only.
- Error responses never expose provider payloads or secrets.

## 21. Performance budgets

- Navigation summary uses one aggregate request.
- Initial lists fetch at most 50 rows.
- Lists exclude full email body and full report/source payload.
- Detail data loads only after selection.
- Do not add a charting library for simple operational counts.
- Local interactions respond within 100 ms.
- Healthy-database list API p95 target: under 500 ms.
- Navigation summary p95 target: under 300 ms.
- Production build passes typecheck with no hydration warnings.

## 22. Implementation phases and commits

Each phase ends with its own verified commit.

### FE-0 — Contract foundation

- Common response schemas.
- Zod contracts.
- Organization-scoped query keys.
- Capability helpers.
- Reason registry.
- Server-time/countdown utility.
- HTTP idempotency utility.
- Vitest and React Testing Library setup.

Gate: typecheck, unit tests, and Docker frontend build.

### FE-1 — User read-only workspace

- Smart Inbox.
- Shared Intelligence Detail.
- Upgraded Research Cases.
- Connection health.
- Navigation summary.
- SSE invalidation and polling fallback.

Side-effect commands remain disabled except mark-read and manual sync.

### FE-2 — Approval actions

- Approval list/detail.
- Risk, mode, expiry, and proposal version.
- Approve/reject/cancel commands.
- 409/412 and verifying-outcome behavior.
- Double-submit and expiry E2E tests.

### FE-3 — Admin observability

- Overview.
- Connections Health.
- Schedulers.
- Read-only Queue/Dead-letter.
- Manual Reviews.
- Trace Explorer.

Admin mutations remain feature-flagged until authorization E2E passes.

### FE-4 — Trusted rules shadow mode

- Rule list/create/edit/disable.
- Dynamic public-domain registry metadata.
- Preview and quotas.
- Shadow decision recording without real auto-create.
- Atomic budget concurrency tests.

### FE-5 — Trusted auto-create rollout

1. Internal test account.
2. One allowlisted organization.
3. Allowlisted user cohort.
4. General availability after metrics and incident review remain acceptable.

Kill switches exist globally and by organization, user, connection, and rule. Disabling auto-create falls back to explicit approval.

## 23. Backend API gaps required for frontend completion

The current frontend and API only partially expose these workflows. Implementation must add or expand:

- Navigation summary and route capabilities.
- Cursor/filter Smart Inbox.
- Aggregate email detail.
- Expanded case detail and capabilities.
- Action proposal list/detail/decision contracts.
- Owner-scoped and capability-aware agent/tool approval list responses; normal users must not receive organization-wide pending approvals.
- Trusted rules, preview, registry metadata, and quotas.
- Atomic user/organization budget reservation.
- Admin overview, connection health, scheduler, dead-letter, reviews, and trace endpoints.
- Resource-change SSE stream.
- Stable error envelope.
- Versioned reason-code registry.
- Server time in time-sensitive responses.

Existing endpoints may retain a compatibility alias for one release, but the frontend uses one canonical namespace per resource. Compatibility code must not duplicate authorization logic.

## 24. Release gates

Production enablement is blocked until all gates pass:

1. Cross-user and cross-organization authorization tests.
2. XSS and security-rendering tests.
3. Approval double-submit and ambiguous-timeout tests.
4. 409/412 conflict behavior tests.
5. Trusted-rule wildcard/public-domain/authentication policy tests.
6. Atomic user and organization budget concurrency tests.
7. Budget replay does not double-consume quota.
8. SSE recovery and polling fallback tests.
9. Signout and organization-switch cache isolation tests.
10. Docker production frontend build and typecheck.
11. Backend migrations and OpenAPI/Zod contract tests.
12. Manual-review and dead-letter observability.
13. Global and scoped kill switches live-tested.
14. Shadow-mode results reviewed before real auto-create rollout.

## 25. Definition of done

The frontend feature is complete when:

- Users can connect personal Google accounts and see health without seeing another user’s data.
- New email appears in Smart Inbox through canonical REST refresh triggered by SSE or polling.
- Email classification, guard, routing, linked research, and proposals are understandable without exposing internal-only navigation.
- Research reports show provenance, missing data, and safe links.
- Approval actions display risk, mode, expiry, and version before decisions.
- Side-effect state is never optimistically fabricated.
- Trusted calendar auto-create is deny-by-default, authenticated-sender-only, quota-bounded, atomic under concurrency, shadow-tested, and kill-switchable.
- Admins can observe operational problems without receiving secrets or unrestricted email content.
- Capability changes, stale versions, network ambiguity, reconnects, signout, and organization switches fail safely.
- Accessibility, security, contract, concurrency, and production-build release gates pass.
