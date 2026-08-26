# Workflow Node Configuration System — Design

**Date:** 2026-08-26
**Status:** Approved (design review)
**Scope:** Upgrade the workflow DAG node system so every node kind has a real, validated configuration schema (n8n-style `properties`), the agent node supports inline/custom configuration, the scheduler node generates cron from a visual form, the integration node calls real Google APIs, and the triager node does real LLM routing. Fix the node config UI to render forms dynamically from backend-declared schemas.

---

## 1. Problem Statement

The current workflow node system is under-realized:

- **Agent node** only picks a pre-existing `Agent` (`agent_id`). It cannot define a system prompt, model, tools, temperature, or iterations inline. `run_agent_loop` already supports `model_id` override but the engine never passes one, and there is no `system_prompt` override path at all.
- **Scheduler node** is a raw cron text input with no validation, no timezone, no visual form.
- **Integration node** returns hard-coded mock data (`engine.py` lines 298–312) despite a complete real Google integration stack existing (OAuth, connections, refresh, MCP providers, 24 builtin tools).
- **Triager node** is a placeholder that concatenates text with a policy label — no real routing.
- **Tool node** requires typing the tool name by hand and passing a loose `config` dict; no dropdown, no argument forms, no description.
- All node config lives in an unvalidated `config: dict[str, Any]` on `GraphNode`. The UI (`workflow-node-config.tsx`) hardcodes a handful of fields per kind.
- Edge conditions are string-only `simpleeval` guards against `output`; they cannot route on structured triager output.

## 2. Goals / Non-Goals

### Goals
- Every node kind has a declared, validated configuration schema (n8n-style `properties` array).
- Agent node: dual mode — inherit an existing agent with per-field overrides, or custom inline config (system prompt, model, tools, temperature, max iterations, thinking).
- Scheduler node: visual form generating a real cron expression + IANA timezone.
- Integration node: real Gmail / Google Calendar / Google Drive / webhook data via the existing CI integration stack — no mocks.
- Triager node: real LLM routing (category + reason) and rule-based fallback; edges can route on structured output.
- Tool node: dropdown of registered tools with argument forms/JSON, descriptions, retry/timeout.
- Frontend renders node forms dynamically from backend-declared `NodeDefinition`s (single source of truth).
- Backend validates node parameters on save; clear per-node/per-field errors.
- **RBAC: role `user` gets `workflows:create/update/delete` (ownership-scoped). Templates are pre-built workflows the user can install and edit as their own.**

### Non-Goals
- No workflow versioning, sharing, or multi-tenant workflow catalog.
- No visual debugger beyond the existing run console.
- No parallel-branch UI beyond current capabilities.
- No new integration connectors beyond what exists (Gmail/Calendar/Drive/webhook).

## 2.5 RBAC — giving `user` full workflow authoring

**Decision:** role `user` can create, edit, and delete workflows. Templates are just pre-built workflows: a user installs a template, gets a real editable `Workflow` DAG, and can modify it to their needs. This matches the n8n/Zapier consumer-turned-builder model and maximizes what a user can do with the system.

### Permission changes (`backend/app/core/authz/policy.py`)

Add to `Role.user`:

```python
"workflows:create",
"workflows:update",
"workflows:delete",
```

(Keep existing `workflows:read`, `workflows:run`, `workflows:install`.)

### Ownership scoping (critical)

The `workflows:*` permissions already exist for `operator` (org-wide). For `user`, the create/update/delete must be **ownership-scoped** so a user can only edit/delete their own workflows:

- Add `created_by_user_id` enforcement on `PUT /api/workflows/{id}` and `DELETE /api/workflows/{id}`: if the caller is `Role.user`, the workflow must have `created_by_user_id == caller.user_id`; otherwise 403.
- `operator`/`org_admin` keep org-wide access unchanged.
- This mirrors the existing `PrincipalContext.owner_user_id` pattern (line 96 of `policy.py`): `user_id` when role is `user`, else `None` (meaning no ownership restriction).

### Template install → editable workflow

- `POST /api/workflow-catalog/installations` already creates a real `Workflow` row (workflow_id unique) plus a `WorkflowInstallation`. Change the flow so the materialized workflow is **fully editable by the installing user**:
  - The created `Workflow` keeps the template's DAG in `graph` (already seeded via `0050_automation_template_dag_graphs.py`), with `created_by_user_id` = the installing user.
  - The `/automations` UI adds an **"Open in editor"** action on an installed template that navigates to `/workflows?edit=<workflow_id>`.
  - Editing an installed template's workflow updates the DAG but keeps the `WorkflowInstallation` schedule wiring (hidden schedule from §5.3) so the user's cron still fires.
- This replaces the current "install creates an opaque workflow" behavior with a transparent, user-owned, editable DAG.

### Permissions on the new endpoints

- `GET /api/workflows/node-definitions`, `GET /api/workflows/node-options`, `GET /api/workflows/tool-options` → require `workflows:read` (user has it).
- Webhook endpoint (§6.2) → unauthenticated (token-verified), as designed.

### RBAC tests

- `test_workflow_rbac.py`: user can create/update/delete their own workflow; 403 on another user's workflow; operator/org_admin unaffected; user can install template then edit the materialized workflow; user can run own + published workflows.

## 3. Research Summary (patterns from industry tools)

- **n8n** — node configuration is a declarative `properties` array of `INodeProperties` (`displayName`, `name`, `type`, `default`, `description`, `placeholder`, `required`). Types: `string`, `number`, `boolean`, `options`, `multiOptions`, `collection`, `fixedCollection`, `dateTime`, `json`, `resourceLocator`, `notice`, `hidden`. Conditional visibility via `displayOptions.show/hide`. Dynamic dropdowns via `loadOptionsMethod` (fetch from API, `loadOptionsDependsOn` re-fetches). Credentials stored separately, encrypted, referenced by id. Resource/Operation pattern: one node = one service; pick resource → operation → fields specific to that operation.
- **Kestra** — triggers are first-class and separate from tasks (`triggers:` vs `tasks:` in flow YAML): schedule, event, webhook.
- **Temporal** — durable execution: activities with retry/heartbeat, signals for human-in-the-loop (matches our approval/resume), durable timers, child workflows (matches `sub_workflow`), Temporal Schedules for cron. Workflow-as-code, event-sourcing replay (matches our `ToolCallRecord` replay).
- **Activepieces** — AI-first: each AI node has its own LLM config (model + prompt + temperature); MCP connections supported.

### Applied to this project
- **n8n `properties` → `NodeDefinition.fields`** (declarative, single source of truth; backend validates, frontend renders).
- **Resource/Operation** for `tool` and `integration` nodes.
- **`displayOptions` → `display`** for conditional fields.
- **`loadOptionsMethod` → `load_options_from`** (tools, models, agents, workflows, connections, users).
- **Kestra-style trigger separation** already exists (scheduler/integration as entry nodes); we unify editor workflows with the Automation Hub scheduler so cron tick fires editor-created workflows with a scheduler node.
- **Temporal-style durability** (lease, resume, approval, replay) is retained as-is.

## 4. Data Model

### 4.1 `NodeField` and `NodeDefinition` (backend, new)

New module: `backend/app/core/workflow/node_definitions.py`.

```python
class NodeField(BaseModel):
    name: str                       # key inside parameters
    label: str                      # UI label
    type: Literal["string","textarea","number","boolean","options",
                  "multiOptions","collection","fixedCollection","json"]
    default: Any = None
    required: bool = False
    description: str = ""
    placeholder: str = ""
    options: list[dict] | None = None          # for options/multiOptions
    load_options_from: Literal["tools","models","agents","workflows",
                               "connections","users","categories"] | None = None
    display: dict[str, Any] | None = None      # n8n displayOptions: {"show": {...}, "hide": {...}}
    type_options: dict[str, Any] = {}          # rows, minValue, maxValue, password, multipleValues
    multiple: bool = False                     # fixedCollection repeatable rows

class NodeDefinition(BaseModel):
    kind: str
    label: str
    description: str
    icon: str = ""
    fields: list[NodeField]
    default_parameters: dict[str, Any] = {}
```

- `NODE_DEFINITIONS: dict[str, NodeDefinition]` — one per kind (`input`, `scheduler`, `integration`, `triager`, `agent`, `tool`, `merge`, `approval`, `sub_workflow`, `output`).
- Exposed via `GET /api/workflows/node-definitions` (returns `dict[kind, NodeDefinition]`).

### 4.2 `GraphNode` (schema change, backward compatible)

`backend/app/schemas/workflow.py`:

```python
class GraphNode(BaseModel):
    id: str
    kind: NodeKind
    label: str = ""
    agent_id: str | None = None        # kept: kind == "agent", mode == "inherit"
    merge_mode: MergeMode = "all"      # kept: kind == "merge"
    parameters: dict[str, Any] = {}    # NEW: validated per NodeDefinition
    config: dict[str, Any] = {}        # DEPRECATED alias, read fallback only
```

- Writer (`POST`/`PUT`) accepts `parameters`; `config` is tolerated for backward compatibility with stored data.
- Reader normalizes: `parameters = node.parameters or node.config or {}`.
- Engine (`engine.py`) reads `parameters` primarily, falls back to `config` keys.

### 4.3 Node parameters per kind (summary)

**`input`**: `input_field` (string), `required` (bool), `description` (string).

**`scheduler`**: `frequency` (options: `once|hourly|daily|weekdays|weekly|custom`), `time` (string HH:MM, when ≠ once), `days_of_week` (multiOptions, when weekdays/weekly), `timezone` (options/IANA, when ≠ once), `custom_cron` (string, when custom), `start_date`/`end_date` (dateTime, optional). Backend derives `cron` + `schedule_label`.

**`integration`**: `source` (options: `gmail|google_calendar|google_drive|webhook`), `connection_id` (load_options_from=connections, per source), `operation` (options per source: gmail `list_new|search|get`; calendar `list_events`; drive `list_files`), `max_results` (number), `query`/`filter` (string, per operation), `time_range` (options: `today|7d|30d|custom`).

**`triager`**: `mode` (options: `llm|rules`), `categories` (string, comma/newline list; can load from edges), `instruction` (textarea, LLM mode), `model_id` (load_options_from=models, optional), `output_format` (options: `category_only|category_with_reason`), `rules` (fixedCollection: `{pattern, category}`) for rules mode.

**`agent`**: `mode` (options: `inherit|custom`). Inherit: `agent_id` (load_options_from=agents), `system_prompt_override`, `model_id_override`, `tools_override` (multiOptions from tools), `temperature_override`, `max_iterations_override`, `enable_thinking_override` (all optional, each with an "override" toggle). Custom: `system_prompt` (textarea, required), `model_id` (load_options_from=models, required), `tools` (multiOptions), `temperature` (number, default 0.7), `max_iterations` (number, default 12), `enable_thinking` (boolean).

**`tool`**: `tool` (load_options_from=tools, required), `arguments` (json, optional; schema-aware if tool declares one), `retry` (collection: `max_attempts`, `backoff_s`), `timeout_s` (number).

**`merge`**: `merge_mode` (options `all|any`, kept on node), `separator` (string, default `\n\n`).

**`approval`**: `title`, `instructions` (string/textarea), `approver_user_ids` (multiOptions from users, optional), `timeout_minutes` (number, optional; expiry = auto-decline).

**`sub_workflow`**: `workflow_id` (load_options_from=workflows, excludes self), `input_mapping` (collection, optional).

**`output`**: `include` (options: `all_inputs|selected`), `selected_from` (multiOptions of upstream node ids), `format` (options: `text|json`).

## 5. Backend Engine Changes

### 5.1 Validation (`workflow_service.py`)

- `validate_graph(graph, org_id)` validates each node's `parameters` against its `NodeDefinition`: required fields, types, allowed options values, valid load_options references (e.g. `model_id` must exist in org).
- Structural validation retained: ≥1 entry node (`input|scheduler|integration`), no cycles (existing DFS), agent custom mode requires `model_id`.
- Returns detailed errors: `{node_id, field, message}` list.

### 5.2 Agent node (`engine.py`)

- **`mode=custom`**: build an in-memory `Agent` (not persisted): `Agent(org_id=..., name=f"workflow-node-{node_id}", system_prompt=..., model_id=..., tools=..., temperature=..., max_iterations=..., enable_thinking=...)`; call `run_agent_loop(agent, text, db, ...)`.
- **`mode=inherit`**: load `Agent` by `agent_id`; apply each override field onto a shallow copy of the agent object before the loop (system_prompt, model_id, tools, temperature, max_iterations, enable_thinking). Keep `agent_release_id` write on the node run.
- Pass `model_id` through to `run_agent_loop` (already supported).
- No fallback to "first agent in org" when custom mode has no agent — custom mode is self-contained. Inherit mode with no `agent_id` errors clearly.

### 5.3 Scheduler node

- New helper `backend/app/core/workflow/schedule.py`: `build_cron(frequency, time, days_of_week, custom_cron, timezone) -> (cron, schedule_label)`; validates with `croniter` (or existing scheduler lib).
- Engine's `scheduler` node returns `input_text or f"[{label}] Automated trigger initiated (schedule: {cron})."` using the derived cron + label.
- Unify with Automation Hub: when a workflow has a `scheduler` node, backend materializes/updates a hidden `WorkflowInstallation` (or `workflow.schedules` JSON field) so the existing 60s cron tick (`run_due_workflows`) fires editor-created workflows. `next_run_at` computed from cron + timezone. Removing the node removes the schedule.

### 5.4 Integration node — real data

Replace the mock block with real provider calls, scoped to `workflow.org_id` + `actor_user_id`, mirroring `backend/app/customer_intelligence/tools.py` `_connected_*` helpers:

- `gmail`: `EmailConnectionRepository` lookup by `connection_id` (or account) → `load_fresh_credentials` → `McpEmailProvider` (`list_new`/`search`/`get`) → summarize `InboundEmail` fields (from/subject/snippet/date) into text.
- `google_calendar`: `CalendarConnectionRepository.get_connected(org_id, user_id)` → `load_fresh_credentials` → calendar provider `list_events(from, to, max_results)` → text lines of events.
- `google_drive`: `DriveConnectionRepository.get_connected(org_id, user_id)` → `McpDriveProvider.list_files` → text lines.
- `webhook`: read payload from the workflow run input (set by webhook endpoint, §6.2).
- If no connection configured/connected → raise a clear error ("integration node requires a connected Gmail connection; connect one in Settings"); no mock fallback.
- `source` values normalized: accept legacy spellings `google_calendar`/`google_drive` from LLM-generated graphs and map them to canonical `google_calendar`/`google_drive` values used by the UI.

### 5.5 Triager node — LLM routing

- `mode=llm`: build prompt from upstream text + categories + instruction; call LLM via existing `build_driver`/LLM client; parse JSON `{"category": "...", "reason": "..."}` (strict `output_format`).
- Return structured output from the node. Engine stores `outputs[node_id]`; for edges, support structured conditions: `_eval_condition` extended so `output` may be a dict — conditions like `output.category == "sales"` evaluate against it; string conditions still work for text outputs.
- `mode=rules`: match each rule's regex/keyword against upstream text; first match wins → category.
- Keep `urgency_and_intent` default categories for LLM mode when none provided.

### 5.6 Edge conditions

- Extend `_eval_condition(cond, output)` to accept `dict` output: pre-bind `output.category`, `output.reason`, and the raw text as `output.text`/`output`. String comparisons against text remain supported.
- UI offers condition autocomplete (`output.category == "sales"`, `output contains "urgent"`, `true`).

### 5.7 Unchanged

Retry/budget/approval/lease/replay/sub_workflow mechanics are retained. Retry config may move into `parameters` but the engine still reads legacy `node.retry`/`config.retry`.

## 6. API & Webhook Changes

### 6.1 New endpoints

- `GET /api/workflows/node-definitions` → `dict[kind, NodeDefinition]`.
- `GET /api/workflows/tool-options` → list of `{name, description, risk_tier}` for tool dropdowns (from `BUILTIN_TOOLS` + MCP tools + CI tools, scoped to org).
- `GET /api/workflows/node-options?type=models|agents|workflows|connections|users` → dynamic dropdown sources for `load_options_from`.

### 6.2 Webhook integration

- New route `POST /api/webhooks/workflow/{workflow_id}/{path}` — unauthenticated, verified by shared token (`workflow_webhook_shared_token` config, mirroring gmail webhook pattern), 1MB body cap.
- On valid request: create `WorkflowRun` (status queued) with `input={"webhook_payload": body, "path": path}` + `WorkflowOccurrence` + outbox event `workflow.run.requested` → worker executes; integration `webhook` node reads `input.webhook_payload`.

## 7. Frontend Changes

### 7.1 Dynamic form renderer

- New `frontend/components/workflows/node-config-form.tsx` — renders fields from `NodeDefinition.fields`:
  - Types: `string` (Input), `textarea` (Textarea, rows from type_options), `number`, `boolean` (Switch), `options` (Select), `multiOptions` (multi-select), `collection` (add-field group), `fixedCollection` (repeatable rows), `json` (JSON editor or textarea with validation).
  - `display`: show/hide per conditions (`{"show": {"mode": ["custom"]}}`).
  - `load_options_from`: fetch via `GET /api/workflows/node-options?type=...` with React Query; refresh on dependent field change.
- `workflow-node-config.tsx` replaced with `NodeConfigForm` + header/delete preserved.
- New hook `useNodeDefinitions()` (key `["workflow-node-definitions"]`).

### 7.2 Types

- `frontend/types/index.ts`: `GraphNode.parameters` added (read fallback to `config`); `NodeField`, `NodeDefinition`, `WorkflowNodeParameters` types.

### 7.3 Node-specific UI

- **Agent**: mode toggle (Inherit/Custom); Inherit shows agent dropdown + per-field override checkboxes; Custom shows full inline form.
- **Scheduler**: frequency segmented control, time picker, weekday chips, timezone select, date range; live cron + label preview.
- **Tool**: tool dropdown (with description), arguments JSON editor, retry/timeout collapsible.
- **Triager**: mode toggle; LLM: categories tag input + instruction + model; Rules: pattern→category table (fixedCollection).
- **Integration**: source dropdown → connections list (with status + Connect button triggering CI OAuth flow) → operation → fields.
- **Edge**: custom edge click → condition panel with autocomplete + quick category picks from upstream triager.
- **Run page** (`/run-workflow`): input form reflects input node `input_field`/`required`/`description`.
- **Template install → editable**: `/automations` Active tab gains **"Open in editor"** per installation → navigates to `/workflows?edit=<workflow_id>`; editing keeps the `WorkflowInstallation` schedule wiring alive.
- **`/workflows` visible to user**: the editor page becomes accessible to role `user` (permissions now granted); navigation entry no longer gated to operator.

## 8. Migration

- Alembic migration: add `parameters` JSON column to `workflows.graph` nodes is not needed (graph is JSON); instead a data migration copies `node.config` → `node.parameters` for existing workflows where `parameters` absent.
- Update seeded template DAGs (`0050_automation_template_dag_graphs.py`) to new `parameters` format.
- Update `workflow_service.generate_graph` LLM system prompt to emit `parameters` per the schemas.

## 9. Testing

- **Backend unit**: `test_workflow_node_validation.py` (per-kind required/type/options), agent custom/inherit (mock `run_agent_loop`), `build_cron` cases + validation, integration node with mocked providers, triager LLM (mock LLM) + rules, `_eval_condition` with dict output, webhook endpoint auth + run creation, node-options endpoints.
- **RBAC**: `test_workflow_rbac.py` — user can create/update/delete own workflow; 403 on another user's workflow; operator/org_admin unaffected; user installs template then edits materialized workflow; user can run own + published workflows.
- **Frontend component**: `node-config-form` renders per definition; display logic; load_options fetch.
- **E2E**: create workflow with custom agent + scheduler + tool via UI, run, assert output (with mocked provider/LLM).

## 10. Implementation Order

1. Backend: `NodeDefinition`/`NodeField` + `node_definitions.py` + `GET /api/workflows/node-definitions` + `node-options` + validation in `workflow_service`.
2. **RBAC**: grant `workflows:create/update/delete` to `user`; ownership-scoped enforcement on update/delete; un-gate `/workflows` UI.
3. Backend engine: agent custom/inherit, scheduler cron helper, integration real providers, triager LLM/rules, `_eval_condition` dict.
4. Migration: backfill `config` → `parameters`, update seeded templates, update LLM generation prompt.
5. Frontend: `NodeConfigForm` + types + hook; replace hardcoded config; per-node UI; edge condition panel; run page input form; "Open in editor" on installed templates.
6. Webhook endpoint + schedule unification (editor workflows with scheduler node fire via cron tick).
7. Tests (backend incl. RBAC + frontend) and docs update.

## 11. Risks / Open Items

- **Real Google API in tests**: integration node tests must mock providers; no live credentials in CI.
- **`croniter` dependency**: confirm it is already available (used by scheduler) or add it.
- **Backward compatibility**: old workflows with `config` must still run (read fallback); write path normalizes to `parameters`.
- **LLM triager cost**: LLM routing runs per execution; budget tracker already caps cost — document that triager LLM calls count toward node budget.
