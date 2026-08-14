# Workflow Template Catalog and Recurring Automation — Design Spec

Date: 2026-08-14
Status: Approved design, ready for implementation planning
Target: Docker Compose/VPS, fewer than 100 users, Google Workspace and personal Gmail

## 1. Product decision

OpenAgent will first serve client-facing knowledge workers in small and medium businesses using
Google Workspace: sales, business development, account management, customer success, consulting,
agency, recruiting, and founders who personally handle customer email and meetings.

The product promise is:

> An AI work assistant that automatically handles email triage, meeting preparation, customer
> research, and follow-up while keeping the user in control of external actions.

OpenAgent will not initially position the catalog as a general Zapier/n8n replacement. The first
catalog deliberately uses the integrations already present in the product: Gmail, Google Calendar,
Google Drive, web/news/company research, memory, internal notifications, and human approval.

## 2. Context and current capabilities

The repository already provides:

- a graph workflow engine with parallel fan-out/fan-in, conditional edges, retries, node timeouts,
  run budgets, durable node checkpoints, DB leases, queue execution, replay, and approval pause;
- user-owned Gmail, Google Calendar, and Google Drive OAuth connections;
- Gmail incremental ingestion, email classification, Customer Intelligence research, calendar
  proposals, trusted rules, audit logs, metrics, and an Approval Center;
- PostgreSQL as business truth, Redis/ARQ as rebuildable execution transport, and an outbox pattern;
- a generic leased scheduler tick through `JobScheduleExecution` and `run_leased_tick`.

The current workflow feature does not yet provide:

- a versioned system template catalog;
- per-user installations with integration bindings and safe settings;
- a generic recurring/event scheduler attached to workflows;
- deterministic binding of trigger/node output into agent prompts and tool arguments;
- a general internal notification resource for workflow outputs;
- one canonical dispatch path between email routing and installed workflow templates.

There is also a contract mismatch to close: the engine executes `approval` and `sub_workflow`, while
the public Pydantic `NodeKind` currently lists only `input`, `agent`, `tool`, `merge`, and `output`.

## 3. Goals

1. Let a user discover a curated workflow, configure it, and enable it without editing a graph.
2. Support hourly, daily, weekdays, weekly, and durable event-driven triggers.
3. Execute each logical occurrence at most once, including across worker restarts and duplicate
   trigger delivery.
4. Keep template definitions immutable and upgradeable while preserving user settings.
5. Preserve approval, ownership, tenant isolation, audit, and idempotency invariants.
6. Keep latency and LLM cost bounded through filtering, batching, caching, and model escalation.
7. Reuse the current workflow engine instead of introducing Temporal or another orchestrator.
8. Provide six market-relevant workflows, with the first three suitable for the initial release.

## 4. Non-goals

- A public third-party marketplace in the first release.
- Arbitrary user-authored cron expressions.
- Auto-sending email without an existing trusted policy.
- Replacing CRM, ERP, project management, or team chat products.
- Supporting connectors that are not currently available in OpenAgent.
- Editing a system-managed installation graph in place.
- Replaying every missed hourly run after extended downtime.
- Cross-organization workflow installations or shared credentials.

## 5. Chosen approach

The selected model is **Template Catalog + Workflow Installation**.

```text
WorkflowTemplate
  └── WorkflowTemplateVersion (immutable)
        └── WorkflowInstallation (owned by one user in one organization)
              ├── WorkflowInstallationBinding
              ├── WorkflowSchedule
              ├── materialized Workflow
              └── WorkflowOccurrence → WorkflowRun
```

System templates are read-only. Installing a template compiles its logical graph into a normal
OpenAgent `Workflow`, resolving logical agent roles and integration bindings. The compiled workflow
is marked system-managed and is not editable in Workflow Builder. A user who wants to edit the graph
must use **Clone as custom workflow**; the clone no longer receives template upgrades.

This preserves the existing engine and visual builder while keeping catalog automations supportable.

## 6. Architecture

```text
Template Catalog API
        │ install / upgrade
        ▼
Installation Compiler ───────────────► managed Workflow + graph checksum
        │
        ├── settings + connection bindings
        └── schedule/event subscription

ARQ minute tick
  → run_leased_tick (one global dispatcher tick)
  → claim due schedules with FOR UPDATE SKIP LOCKED
  → create WorkflowOccurrence + WorkflowRun + outbox atomically
  → queue workflow run

Gmail routed event
  → outbox event
  → event subscription matcher
  → create WorkflowOccurrence + WorkflowRun + outbox atomically
  → queue workflow run

Workflow engine
  → deterministic interpolation
  → agents/tools in parallel
  → approval for side effects
  → internal notification / report
```

PostgreSQL remains canonical for templates, installations, schedules, occurrences, runs, approvals,
and notifications. Redis contains only queue transport and rate-limit state.

## 7. Domain model

All persisted datetimes use naive UTC following the existing model convention. User-facing schedule
calculations use the installation timezone, defaulting to `Asia/Ho_Chi_Minh`.

### 7.1 `workflow_templates`

One stable catalog identity across versions.

| Column | Type | Rule |
|---|---|---|
| `id` | UUID string | Primary key |
| `key` | string(96) | Unique stable key, for example `morning-command-center` |
| `name` | string(160) | User-facing name |
| `description` | text | Catalog description |
| `category` | string(48) | `daily_planning`, `meetings`, `follow_up`, `customer_intelligence`, `reporting` |
| `icon` | string(64) | Approved Lucide icon key |
| `status` | string(24) | `draft`, `published`, `deprecated` |
| `release_tier` | string(16) | `p0`, `p1` |
| `risk_level` | string(16) | `low`, `medium`, `high` |
| `current_version_id` | FK nullable | Published version shown by default |
| `created_at`, `updated_at` | datetime | Audit timestamps |

Only application migrations or an admin-only publishing command may create/publish system templates
in phase one. There is no user-facing template authoring endpoint.

### 7.2 `workflow_template_versions`

An immutable published definition.

| Column | Type | Rule |
|---|---|---|
| `id` | UUID string | Primary key |
| `template_id` | FK | Cascade delete only while template is unpublished |
| `version` | integer | Unique with `template_id` |
| `graph` | JSON | Logical, unresolved graph |
| `config_schema` | JSON Schema | User-configurable settings |
| `output_schema` | JSON Schema | Canonical result contract |
| `integration_requirements` | JSON | Required/optional binding keys and OAuth scopes |
| `trigger_schema` | JSON | Allowed schedule/event trigger types and limits |
| `policy` | JSON | Approval, concurrency, budget, retention defaults |
| `managed_agent_specs` | JSON | Logical agent roles, prompts, tool allowlists, model tier |
| `checksum_sha256` | string(64) | Server-computed canonical checksum |
| `changelog` | text | Upgrade summary |
| `published_at` | datetime nullable | Once set, row is immutable |

Published rows cannot be updated. A changed graph, prompt, schema, tool allowlist, or policy creates a
new version.

### 7.3 `workflow_installations`

One user-owned installation. Multiple installations of the same template are allowed so a user can
bind separate accounts or schedules.

| Column | Type | Rule |
|---|---|---|
| `id` | UUID string | Primary key |
| `org_id` | FK | Indexed tenant scope |
| `owner_user_id` | FK | Installation owner |
| `template_id` | FK | Catalog identity |
| `template_version_id` | FK | Pinned immutable version |
| `workflow_id` | FK unique | Materialized managed workflow |
| `name` | string(160) | User override, unique per owner/org |
| `status` | string(32) | See lifecycle below |
| `settings` | JSON | Validated against `config_schema` |
| `policy_snapshot` | JSON | Effective immutable policy for current version |
| `timezone` | string(64) | Valid IANA zone; default `Asia/Ho_Chi_Minh` |
| `daily_cost_limit_usd` | decimal | Server-capped user budget |
| `last_success_at` | datetime nullable | Health summary |
| `last_error_code` | string nullable | Redacted stable code |
| `created_at`, `updated_at` | datetime | Audit timestamps |

Statuses:

```text
DRAFT → VALIDATING → ENABLED
ENABLED ↔ PAUSED
ENABLED/PAUSED → NEEDS_REAUTHORIZATION
ENABLED/PAUSED → DEGRADED
any non-deleted → DISABLED
DISABLED → ENABLED only after full validation
```

`DEGRADED` permits read-only/partial output when one optional branch fails. It does not permit a
side effect whose prerequisites are unavailable.

### 7.4 `workflow_installation_bindings`

| Column | Type | Rule |
|---|---|---|
| `id` | UUID string | Primary key |
| `installation_id` | FK | Cascade delete |
| `binding_key` | string(64) | Such as `primary_gmail`, `primary_calendar`, `report_drive` |
| `connection_type` | string(24) | `gmail`, `calendar`, `drive` |
| `connection_id` | UUID string | Application-validated connection reference |
| `required` | boolean | Copied from template version |
| `created_at` | datetime | Audit timestamp |

Unique constraint: `(installation_id, binding_key)`. The API verifies the referenced connection is
connected, belongs to the same org, and is owned by the installation owner unless an explicit shared
connection policy grants access. Queue payloads are never trusted for ownership.

Credentials are not copied into installations, graphs, schedules, occurrences, or queue payloads.

### 7.5 `workflow_schedules`

| Column | Type | Rule |
|---|---|---|
| `id` | UUID string | Primary key |
| `installation_id` | FK | Cascade delete |
| `trigger_type` | string(24) | `hourly`, `daily`, `weekdays`, `weekly`, `event` |
| `configuration` | JSON | Validated trigger-specific values |
| `timezone` | string(64) | Copied from installation unless overridden |
| `enabled` | boolean | Dispatch gate |
| `next_run_at` | datetime nullable | Canonical UTC due time; null for event trigger |
| `last_dispatched_at` | datetime nullable | Operations visibility |
| `created_at`, `updated_at` | datetime | Audit timestamps |

Phase-one constraints:

- one active schedule per installation;
- hourly interval must be one of `1`, `2`, `3`, `4`, `6`, or `12` hours;
- daily/weekdays/weekly use `HH:MM` and an IANA timezone;
- weekly accepts exactly one weekday;
- no raw cron expression;
- event schedules bind to one supported event type and one connection.

### 7.6 `workflow_occurrences`

This is the entity-level idempotency and operations record. It is separate from
`job_schedule_executions`, which prevents multiple workers from executing the same global scheduler
tick.

| Column | Type | Rule |
|---|---|---|
| `id` | UUID string | Primary key |
| `org_id` | FK | Tenant scope |
| `installation_id` | FK | Owning installation |
| `schedule_id` | FK nullable | Null only for manual run |
| `trigger_type` | string(24) | Schedule, event, or manual |
| `scheduled_for` | datetime | Logical UTC occurrence time |
| `trigger_dedupe_key` | string(256) | Event ID or canonical scheduled time |
| `status` | string(32) | `created`, `queued`, `running`, terminal values below |
| `workflow_run_id` | FK unique nullable | Materialized run |
| `attempt_count` | integer | Dispatch attempts, not node attempts |
| `skip_reason` | string nullable | Stable reason code |
| `created_at`, `finished_at` | datetime | Audit timestamps |

Unique constraint:

```text
(installation_id, trigger_type, trigger_dedupe_key)
```

Terminal statuses: `succeeded`, `partial`, `failed`, `skipped_overlap`, `skipped_budget`,
`cancelled`, `dead_letter`.

### 7.7 General workflow notifications

`ci_notifications` requires an email and therefore cannot represent morning, meeting, or weekly
reports. Add a general `notifications` table:

| Column | Type | Rule |
|---|---|---|
| `id` | UUID string | Primary key |
| `org_id`, `user_id` | FK | Tenant and recipient |
| `source_type` | string(32) | `workflow_run`, `approval`, `system` |
| `source_id` | UUID string | Source resource |
| `notification_type` | string(48) | Stable registry code |
| `severity` | string(16) | `info`, `attention`, `warning` |
| `title` | string(320) | Safe plain text |
| `summary` | text | Safe plain text |
| `payload` | JSON | Validated structured card data, no credentials/raw HTML |
| `read_at`, `created_at` | datetime | State and audit |

Unique constraint: `(user_id, source_type, source_id, notification_type)`.

Approval notifications remain backed by canonical `ApprovalRequest`; notification rows are only a
discoverability surface and never an authorization source.

## 8. Template compilation

Template graphs use logical references, not organization-specific UUIDs:

```json
{
  "kind": "agent",
  "config": {"agent_role": "email_triage"}
}
```

On installation or upgrade, the compiler:

1. validates the template checksum and all schemas;
2. verifies required integration bindings and OAuth scopes;
3. creates or reuses system-managed agents/releases for each logical role;
4. resolves `agent_role` to an `agent_id` in the installation's organization;
5. validates every tool against the role's allowlist;
6. writes a materialized `Workflow` with `managed_by="template"` and an installation reference;
7. stores the compiled graph checksum;
8. creates the schedule in disabled state;
9. enables only after a dry validation succeeds.

Compilation is transactional. No schedule is enabled if any step fails.

The `Workflow` model receives additive fields: `managed_by`, `installation_id`,
`template_version_id`, and `graph_checksum`. Workflow update/delete endpoints reject direct changes
to a system-managed workflow; lifecycle changes go through installation APIs.

## 9. Workflow graph contract extensions

### 9.1 Node kinds

Public backend/frontend schemas must align with the engine:

```text
input | agent | tool | merge | approval | sub_workflow | output
```

### 9.2 Structured run context

Every run receives:

```json
{
  "trigger": {
    "type": "schedule",
    "scheduled_for": "2026-08-15T00:30:00Z",
    "event_id": null,
    "payload": {}
  },
  "installation": {
    "id": "...",
    "timezone": "Asia/Ho_Chi_Minh",
    "settings": {}
  },
  "bindings": {
    "primary_gmail": {"connection_id": "..."}
  }
}
```

The server creates this context from canonical DB records. Clients and queue messages cannot inject
connection IDs or policy snapshots.

### 9.3 Deterministic interpolation

Agent prompt templates and tool argument JSON support references:

```text
${trigger.payload.email_id}
${trigger.scheduled_for}
${installation.settings.follow_up_hours}
${nodes.gmail_scan.output.items}
```

Rules:

- JSONPath-like property lookup only; no `eval`, functions, arithmetic, or arbitrary expressions;
- missing required reference fails node validation before tool execution;
- output inserted into JSON preserves its native type;
- output inserted into a string is escaped as text;
- maximum expanded prompt and argument sizes are enforced;
- secret/credential fields are not addressable;
- untrusted email/web content is delimited when passed to an agent.

Conditional edges continue using the existing restricted evaluator, but template publishing accepts
only a documented allowlist of expressions and validates them against fixture outputs.

### 9.4 Agent prompt templates

The engine must apply `config.prompt_template` for agent nodes. If absent, it preserves the current
behavior of concatenating upstream output. Template-managed agent prompts are immutable within a
published version and include output JSON schemas for downstream parsing.

### 9.5 Tool nodes and approval

Read-only tools may execute directly. The following classes require approval unless an existing
server-side trusted rule explicitly permits them:

- Gmail draft creation, reply, forward, send, trash, label mutation;
- Calendar create, update, or delete;
- Drive create, update, or delete;
- durable memory/knowledge writes designated by policy.

The LLM never decides whether approval is bypassed. A deterministic policy router evaluates guard
outcome, tool, owner, trusted rule snapshot, expiry, quota, and payload hash.

## 10. Scheduler and event dispatch

### 10.1 Global scheduler tick

ARQ runs a one-minute cron. It calls `run_leased_tick` with a new stable job key
`workflow_schedule_dispatch`. `JobScheduleExecution` ensures only one worker executes a logical
minute tick.

Inside the claimed tick:

1. select due enabled schedules ordered by `next_run_at`, bounded to 100;
2. claim rows using `FOR UPDATE SKIP LOCKED` on PostgreSQL;
3. validate installation status and connection health;
4. create occurrence, workflow run, and outbox event in one transaction;
5. advance `next_run_at` using wall-clock schedule plus IANA timezone;
6. commit before Redis publication.

SQLite tests use a repository fallback with equivalent single-worker semantics.

### 10.2 Event dispatch

Event sources publish durable outbox events. Initial registry:

```text
gmail.message.routed.v1
```

The event payload contains only stable IDs, classification/routing metadata, correlation ID, and
event version. The consumer reloads email and connection ownership from PostgreSQL before creating
an occurrence.

The dedupe key for New Customer Intelligence is:

```text
gmail-message-routed:{connection_id}:{provider_message_id}:{classification_version}
```

There must be exactly one canonical path from routed email to customer research. The existing direct
classification-to-research dispatch is replaced behind a feature flag by the installation event
dispatcher. During migration, shadow dispatch records decisions without creating a second case.

### 10.3 Overlap and missed-run policy

Default concurrency policy is `FORBID`: one running occurrence per installation. A due occurrence
while another is active becomes `skipped_overlap`; it is not queued behind indefinitely.

After downtime:

- hourly workflows create at most one catch-up occurrence for the latest missed window;
- daily/weekdays/weekly workflows create at most one catch-up occurrence if less than 12 hours late;
- older scheduled occurrences are recorded `skipped_missed_window`;
- event occurrences are never coalesced and remain durable until processed or dead-lettered.

This avoids a restart storm while preserving event correctness.

### 10.4 Enable, pause, and disable semantics

- Enable validates version, bindings, scopes, schedule, budget, and compiled graph.
- Pause prevents new occurrences but does not cancel a claimed run.
- Disable prevents new occurrences and event matching; in-flight runs remain canonical.
- Delete is allowed only after disable and uses soft delete for 30 days.
- Reauthorization failure changes status to `NEEDS_REAUTHORIZATION` and suppresses dispatch.

## 11. Catalog workflows

### 11.1 P0 — Morning Command Center

**Purpose:** produce a concise plan for the user's workday.

Default trigger: weekdays at `07:30`, installation timezone.
Required bindings: Gmail, Calendar.
Optional binding: Drive.
Side effects: none; internal notification only.
Default budget: 2 LLM calls, 30 email candidates, 20 calendar events, USD 0.08/run.

Configuration:

```json
{
  "lookback_hours": 24,
  "calendar_horizon_hours": 36,
  "max_email_candidates": 30,
  "include_weekends": false,
  "vip_domains": [],
  "language": "vi"
}
```

Graph:

```text
schedule input
  ├── Gmail metadata scan → deterministic candidate filter → batch triage agent
  └── Calendar scan
          ↓
        merge
          ↓
   priority planning agent
          ↓
 internal notification output
```

Output sections: `needs_response`, `meetings_to_prepare`, `deadlines`, `for_information`, and
`top_priorities`. Every item links to its source email/event. No claim is shown without a source ID.

### 11.2 P0 — Meeting Preparation

**Purpose:** create a briefing before customer meetings.

Default trigger: hourly.
Window: events starting 2–24 hours ahead.
Required bindings: Calendar, Gmail.
Optional binding: Drive.
Side effects: internal report; Drive save requires explicit approval.
Default budget: 4 LLM calls, 10 web sources/event, USD 0.20/event.

Meeting dedupe key:

```text
{calendar_connection_id}:{provider_event_id}:{event_updated_at}
```

Graph:

```text
calendar scan → eligible meeting filter
  ├── related Gmail/thread search
  ├── related Drive search
  └── cached company web/news research
              ↓
            merge
              ↓
        briefing agent
              ↓
 internal notification ── optional approval → Drive report
```

Output sections: meeting objective, attendees, company overview, relationship context, recent news,
open questions, suggested agenda, and sources. If company matching is uncertain, the report says so
and suppresses unrelated web research.

### 11.3 P0 — Follow-up Radar

**Purpose:** detect customer conversations that need attention.

Default trigger: every 2 hours on weekdays between `08:00` and `18:00`.
Required binding: Gmail.
Optional binding: Calendar.
Side effects: proposed text is internal; creating a Gmail draft requires approval.
Default budget: 2 LLM calls, 40 metadata candidates, 12 full threads, USD 0.10/run.

Configuration:

```json
{
  "customer_reply_sla_hours": 24,
  "outbound_wait_hours": 72,
  "max_threads": 12,
  "exclude_internal_domains": true,
  "vip_domains": [],
  "working_hours": {"start": "08:00", "end": "18:00"}
}
```

Deterministic filters remove no-reply senders, newsletters, spam, bulk mail, internal-only threads,
already-completed follow-ups, and threads outside the configured window before LLM use.

Output groups: `user_owes_reply`, `waiting_on_customer`, `commitment_due`, and `suggested_follow_up`.
The workflow never sends automatically in phase one.

### 11.4 P1 — New Customer Intelligence

**Purpose:** productize the existing event-driven customer research pipeline.

Trigger: `gmail.message.routed.v1`.
Required binding: Gmail.
Optional bindings: Calendar, Drive.
Side effects: calendar proposal, Drive save, or email action require approval/trusted policy.
Default budget: economy classification plus up to USD 0.25 for accepted customer research.

Only agent-classified customer/partner messages with sufficient company/contact evidence create a
Research Case. Spam, newsletter, transactional, personal, and unresolved messages do not create an
empty report. One provider message creates at most one Research Case.

If one email contains both customer research and meeting intent, the same case fans out into research
and one calendar proposal. It does not create a second report.

### 11.5 P1 — End-of-day Client Digest

**Purpose:** close the workday and prepare tomorrow.

Default trigger: weekdays at `17:30`.
Required bindings: Gmail, Calendar.
Side effects: internal notification only by default; Drive save requires approval.
Default budget: 2 batch LLM calls, USD 0.10/run.

Output sections: customer interactions, decisions, commitments, unfinished follow-ups, pending
approvals, and tomorrow's important meetings. It reuses classifications/reports created during the
day and does not repeat company web research.

### 11.6 P1 — Weekly Account Review

**Purpose:** show account managers/founders the state of customer relationships.

Default trigger: Friday at `16:00`.
Required bindings: Gmail, Calendar.
Optional binding: Drive.
Side effects: internal report; Drive save requires approval.
Default budget: USD 0.35/run, maximum 20 company domains.

Data is grouped by verified company domain. Output includes interaction level, important messages and
meetings, open commitments, inactivity risk, opportunities, suggested next action, confidence, and
source links. Public email domains are grouped by verified contact, not by domain.

## 12. Cost and latency controls

### 12.1 Filtering and batching

1. Query bounded metadata before fetching bodies or calling an LLM.
2. Use deterministic filters for time window, labels, sender type, no-reply, bulk headers, thread
   status, and dedupe.
3. Fetch full bodies only for bounded candidates.
4. Batch compatible candidates into one structured classification request.
5. Use the economy model for triage and a strong model only for low-confidence/high-value synthesis.
6. Strong-model escalation is bounded per run and per user.

### 12.2 Cache

- company profile cache: 7 days;
- official website pages: 24 hours;
- news search: 6 hours;
- meeting briefing: keyed by event update timestamp;
- email classification: keyed by content hash and classifier version;
- daily/weekly summaries reuse canonical prior outputs rather than re-researching.

Cache provenance and retrieval time remain visible in reports.

### 12.3 Budgets and backpressure

Budgets apply at template-version, installation-day, user, organization, and provider/model levels.
PostgreSQL stores durable daily consumption; Redis token buckets regulate short bursts.

When a run reaches budget:

- stop scheduling optional branches;
- use cached/canonical data;
- create a partial report with `budget_limited=true`;
- never bypass approval or omit provenance;
- record `workflow_budget_limited_total` with bounded labels.

Per-user defaults: two concurrent workflow runs, one concurrent research-heavy run, and 20 pending
occurrences. Queue age limits prevent stale hourly work from consuming capacity after newer work.

### 12.4 Initial service targets

| Workflow | p95 target | Cost target |
|---|---:|---:|
| Morning Command Center | 45 seconds | ≤ USD 0.08/run |
| Meeting Preparation | 60 seconds/event | ≤ USD 0.20/event |
| Follow-up Radar | 35 seconds | ≤ USD 0.10/run |
| New Customer Intelligence | 60 seconds | ≤ USD 0.25/case |
| End-of-day Digest | 45 seconds | ≤ USD 0.10/run |
| Weekly Account Review | 90 seconds | ≤ USD 0.35/run |

These are benchmark acceptance targets, not guarantees for uncontrolled Internet providers.

## 13. API surface

All responses include server-computed `capabilities`; the frontend does not infer permission from
role.

### Catalog

```text
GET  /api/workflow-templates
GET  /api/workflow-templates/{key}
GET  /api/workflow-templates/{key}/versions/{version}
POST /api/workflow-templates/{key}/preview-installation
```

### Installations

```text
GET    /api/workflow-installations
POST   /api/workflow-installations
GET    /api/workflow-installations/{id}
PATCH  /api/workflow-installations/{id}
DELETE /api/workflow-installations/{id}
POST   /api/workflow-installations/{id}/validate
POST   /api/workflow-installations/{id}/enable
POST   /api/workflow-installations/{id}/pause
POST   /api/workflow-installations/{id}/disable
POST   /api/workflow-installations/{id}/run-now
POST   /api/workflow-installations/{id}/upgrade-preview
POST   /api/workflow-installations/{id}/upgrade
POST   /api/workflow-installations/{id}/clone-custom
```

Mutation requests require `Idempotency-Key` and `expected_version`. API idempotency is independent
from occurrence/tool/provider idempotency.

`run-now` creates a normal occurrence with a server-generated dedupe key and does not bypass budget,
approval, overlap, or integration validation.

### Activity and notifications

```text
GET  /api/workflow-installations/{id}/occurrences
GET  /api/workflow-occurrences/{id}
GET  /api/notifications
POST /api/notifications/{id}/read
```

## 14. Frontend experience

### 14.1 Workflow Library

Cards show purpose, required integrations, default cadence, estimated cost tier, approval behavior,
release tier, and whether the template is already installed. P1 templates remain behind a feature
flag rather than appearing as nonfunctional controls.

### 14.2 Installation wizard

1. Overview and example output.
2. Select/authorize required Google connections.
3. Configure workflow-specific settings.
4. Choose cadence and timezone.
5. Review permissions, side effects, approval policy, and budget.
6. Validate and enable.

No installation becomes active before server validation. A test run is read-only: side-effecting
nodes end at proposal preview and cannot call providers.

### 14.3 My Automations

Each installation shows enabled/paused/degraded state, next run in Vietnam/user time, last outcome,
cost today, pending approval count, and actions derived from capabilities. Enable/pause is prominent;
editing the managed graph is absent.

### 14.4 Activity

Activity displays occurrences and node-level execution, partial output, stable error codes, approvals,
and source links. SSE only signals that data changed; REST remains canonical.

### 14.5 Notifications

The global bell and Dashboard surface urgent/attention workflow notifications. Morning/meeting/digest
reports open in a structured detail view. Approval cards link to the existing Approval Center.

## 15. Authorization and security invariants

1. Every installation, binding, schedule, occurrence, run, and notification is organization-scoped.
2. A normal user may manage only installations they own. Admin access follows explicit capabilities.
3. The worker reloads ownership, connection status, OAuth scopes, policy, and template version from DB.
4. Queue/event payloads cannot choose another user's connection.
5. Template graphs and prompts contain no credentials or decrypted tokens.
6. Published version checksum is verified before compile/upgrade.
7. Email/web/tool output is untrusted data and is delimited before LLM calls.
8. Guard outcomes flow into deterministic policy; prompt injection flags cannot become commands.
9. URLs retain SSRF/private-network controls and redirect validation.
10. Side effects require approval or a valid server-side trusted rule snapshot.
11. Approval binds owner, tool, proposal version, payload hash, scope, and expiry.
12. Disabling an installation does not claim an already-running provider action was cancelled.
13. Logs and traces exclude bodies, tokens, credentials, and raw sensitive payloads by default.
14. Template output is rendered as safe structured data/Markdown; raw HTML is not executed.

## 16. Failure handling

Failure categories:

- `TRANSIENT_PROVIDER`: exponential backoff with full jitter, maximum five attempts;
- `RATE_LIMITED`: honor provider retry time and durable `next_allowed_at`;
- `AUTH_REQUIRED`: installation becomes `NEEDS_REAUTHORIZATION`, no automatic retry;
- `INVALID_CONFIGURATION`: installation becomes `DEGRADED` or remains disabled;
- `POLICY_REJECTED`: no retry; create a new proposal/configuration;
- `BUDGET_EXCEEDED`: partial output or `skipped_budget`;
- `AMBIGUOUS_SIDE_EFFECT`: manual review; never resend/recreate blindly;
- `PERMANENT_PROVIDER`: dead-letter after bounded attempts.

One optional branch failure does not fail the whole report. The output marks missing sections and
their stable warning codes. A required-source or security failure fails closed.

## 17. Observability

Metrics use bounded labels only:

```text
workflow_installations_total{template_key,status}
workflow_occurrences_total{template_key,trigger_type,result}
workflow_occurrence_duration_seconds{template_key}
workflow_occurrence_queue_age_seconds{template_key}
workflow_template_cost_usd_total{template_key,model_tier}
workflow_budget_limited_total{template_key,scope}
workflow_schedule_lag_seconds{trigger_type}
workflow_notification_total{notification_type}
```

Logs/traces include correlation ID, installation ID, occurrence ID, workflow run ID, template key and
version, but redact raw email/contact content. Alerts:

- dispatcher has no successful tick for three minutes;
- p95 schedule lag exceeds five minutes;
- event occurrence queue age exceeds two minutes;
- failure rate exceeds 10% for 15 minutes;
- any template produces duplicate occurrence constraint conflicts above expected redelivery levels;
- approval/manual-review age exceeds policy SLA;
- daily organization cost exceeds 80% or 100% of budget.

## 18. Retention

- successful occurrence and node detail: 30 days;
- failed/dead-letter/manual-review occurrence: 90 days;
- notifications: 90 days unless user deletes sooner;
- audit events: 365 days;
- cached public research: per freshness policy, metadata retained 30 days;
- email bodies/attachments: existing Customer Intelligence retention policy;
- template/version/install records: retained while referenced; published versions are not hard-deleted.

Cleanup is a leased scheduled job and never deletes active approvals or in-flight runs.

## 19. Migration and compatibility

Migrations are additive. Implementation planning must choose the next available Alembic revision at
execution time rather than relying on a revision number in this document.

Cutover sequence:

1. Add tables, indexes, workflow managed-source columns, APIs, and feature flags with no dispatch.
2. Seed six templates and publish P0 versions; keep catalog hidden.
3. Add installation compiler and read-only validation/test mode.
4. Add schedule dispatcher in shadow mode; compare expected occurrences without creating runs.
5. Enable P0 for internal users, then one organization, then selected users.
6. For New Customer Intelligence, emit `gmail.message.routed.v1` while old dispatch remains canonical.
7. Verify shadow dedupe/route parity, then switch a per-org flag so installation dispatch becomes the
   sole case creator.
8. Remove the old direct dispatch only after all enabled organizations have migrated.
9. Enable P1 templates incrementally.

Existing custom workflows remain editable and runnable. Existing `CiSchedule` continues to own Gmail
sync cadence; it is not reused as the generic workflow schedule.

## 20. Testing strategy

### 20.1 Unit and contract tests

- schema validation for every template config/trigger/output fixture;
- published template immutability and checksum verification;
- compiler resolves only same-org managed agents and user-owned bindings;
- interpolation preserves JSON types, escapes strings, rejects missing/secret/oversized paths;
- Pydantic/frontend node kinds match engine node kinds;
- timezone calculations cover Vietnam time, UTC, DST zones, month/year boundaries;
- cost/budget arithmetic and atomic reservation under concurrent runs;
- side-effect nodes cannot execute without approval/trusted policy.

### 20.2 Scheduler concurrency tests

- two dispatcher replicas claim one global tick;
- two workers see one due installation and create one occurrence/run;
- duplicate event delivery creates one occurrence;
- restart after occurrence commit but before Redis publish is recovered by outbox;
- overlap creates `skipped_overlap` and no second run;
- downtime coalesces schedules according to policy;
- schedule enable/disable races do not dispatch after disable commit.

### 20.3 Workflow fixtures

Each of six templates has deterministic fake Gmail/Calendar/Drive/research/model fixtures covering:

- normal success;
- no relevant data;
- partial provider failure;
- rate limit;
- prompt injection content;
- cross-user binding attempt;
- budget limit;
- approval approved/rejected/expired;
- retry without duplicate side effect;
- structured output completeness and provenance.

### 20.4 E2E tests

- install P0 template, bind accounts, configure Vietnam timezone, enable, and run now;
- pause prevents scheduled dispatch;
- connection revoked changes installation state and exposes reconnect CTA;
- global bell receives the output notification;
- approval appears without navigating directly to Approval Center;
- org switch/signout clears installation and notification query caches;
- managed workflow cannot be edited, while cloned custom workflow can;
- upgrade preview shows changed permissions/settings and preserves compatible values.

### 20.5 Load and chaos tests

For the target deployment, simulate 100 users with six installations each, simultaneous morning
schedules, provider 429/5xx, Redis restart, worker kill during node execution, API restart, and slow
LLM/research providers. Acceptance requires no duplicate occurrence or provider side effect and no
cross-tenant data exposure.

## 21. Release gates

P0 cannot leave internal rollout until:

- backend test suite, frontend typecheck/build, migration upgrade, and compose E2E pass;
- duplicate occurrence count is zero under concurrency/chaos fixtures;
- all side-effect fixtures require approval by default;
- schedule lag p95 is under five minutes at target load;
- report provenance and missing-data warnings pass deterministic evaluation;
- per-template cost and latency targets are measured and displayed;
- reconnect, pause, disable, and rollback have been exercised;
- backup and restore preserve installations, schedules, occurrences, runs, and approvals;
- no secrets or raw sensitive bodies appear in logs/traces.

## 22. Rollout phases

### Phase 1 — Foundation

Models/migrations, catalog read APIs, template seeding, node-kind alignment, interpolation, compiler,
and feature flags. No automatic dispatch.

### Phase 2 — Scheduler and operations

Schedules, occurrences, outbox dispatch, run-now, Activity, metrics, and Admin Operations visibility.
Shadow scheduling first.

### Phase 3 — P0 catalog

Morning Command Center, Meeting Preparation, and Follow-up Radar for internal users, then one org,
then allowlisted users. Side effects remain explicit approval.

### Phase 4 — Event cutover and P1

New Customer Intelligence single-path cutover, End-of-day Client Digest, and Weekly Account Review.

### Phase 5 — General availability

Upgrade UX, operational runbooks, load/chaos/security gates, backup restore drill, cost dashboards,
and controlled GA for fewer than 100 users.

## 23. Configuration keys

```text
OPENAGENT_WORKFLOW_CATALOG_ENABLED=false
OPENAGENT_WORKFLOW_TEMPLATE_P0_ENABLED=false
OPENAGENT_WORKFLOW_TEMPLATE_P1_ENABLED=false
OPENAGENT_WORKFLOW_SCHEDULER_ENABLED=false
OPENAGENT_WORKFLOW_SCHEDULER_SHADOW=true
OPENAGENT_WORKFLOW_SCHEDULER_BATCH_SIZE=100
OPENAGENT_WORKFLOW_MAX_PENDING_PER_USER=20
OPENAGENT_WORKFLOW_MAX_CONCURRENT_PER_USER=2
OPENAGENT_WORKFLOW_MAX_RESEARCH_CONCURRENT_PER_USER=1
OPENAGENT_WORKFLOW_DEFAULT_DAILY_COST_USD=1.00
OPENAGENT_WORKFLOW_MAX_DAILY_COST_USD=5.00
OPENAGENT_WORKFLOW_NOTIFICATION_RETENTION_DAYS=90
OPENAGENT_WORKFLOW_OCCURRENCE_RETENTION_DAYS=30
OPENAGENT_WORKFLOW_FAILED_RETENTION_DAYS=90
OPENAGENT_CI_EVENT_INSTALLATION_DISPATCH=false
```

Production startup validates budget bounds, encryption/JWT secrets, PostgreSQL/Redis connectivity,
and enabled Google OAuth configuration. Development defaults are not accepted when
`OPENAGENT_RUNTIME=production`.

## 24. Final invariants

1. A system template version is immutable after publication.
2. An enabled installation always references one valid template version and materialized graph.
3. A logical schedule/event occurrence creates at most one workflow run.
4. A routed Gmail message creates at most one customer Research Case.
5. A combined customer-and-calendar email creates one report plus at most one calendar proposal.
6. PostgreSQL is canonical; Redis loss cannot lose an accepted occurrence.
7. A workflow cannot use a connection merely because its ID appears in input or queue payload.
8. LLM output cannot authorize or directly dispatch an external side effect.
9. Every external side effect is approval-gated or covered by a valid server-side trusted rule.
10. Pause/disable stops new dispatch but does not falsify in-flight state.
11. Every user-visible external claim has provenance or an explicit missing-data warning.
12. Budget pressure degrades optional work; it never weakens security or idempotency.
