# Workflow Node Configuration System — Design

**Date:** 2026-08-26
**Status:** Approved (design review)
**Scope:** Upgrade the workflow DAG node system so every node kind has a real, validated configuration schema (n8n-style `properties`), the agent node supports inline/custom configuration, the scheduler node generates cron from a visual form, the integration node calls real Google APIs, and the triager node does real LLM routing. Add structured data-flow between nodes, a unified node output contract, per-node error semantics, an enriched in-editor run view (KPI strip + per-node trace + event log, single page), and a four-tier test plan.

---

## 1. Problem Statement

The current workflow node system is under-realized:

- **Agent node** only picks a pre-existing `Agent` (`agent_id`). It cannot define a system prompt, model, tools, temperature, or iterations inline. `run_agent_loop` already supports `model_id` override but the engine never passes one, and there is no `system_prompt` override path at all.
- **Scheduler node** is a raw cron text input with no validation, no timezone, no visual form.
- **Integration node** returns hard-coded mock data (`engine.py` lines 298–312) despite a complete real Google integration stack existing (OAuth, connections, refresh, MCP providers, 24 builtin tools).
- **Triager node** is a placeholder that concatenates text with a policy label — no real routing.
- **Tool node** requires typing the tool name by hand and passing a loose `config` dict; no dropdown, no argument forms, no description.
- **Data-flow is text-only**: downstream nodes receive `"\n\n".join(inputs.values())`. There is no way for a node to reference a structured field from an upstream node (e.g. email subject, meeting time).
- **No unified output contract**: the engine returns `str` everywhere and stores `{"text": result}`. Structured outputs (triager category, integration payload) have no home.
- **No per-node error semantics**: a node failure aborts the whole workflow; there is no `onError: continue`/`fallback`.
- **No fan-out concurrency limit**: `asyncio.gather` runs every ready node at once, each with its own DB session — a wide fan-out can exhaust the connection pool.
- **Run view is under-realized**: run history is reconstructed as a raw text console; there is no KPI summary (duration/tokens/cost), no per-node trace, no canvas status highlight.
- **Editor workflows with a scheduler node never fire** on the cron tick — only template installations do. The two scheduler paths are not unified.
- **RBAC**: role `user` cannot create/edit workflows; templates install as an opaque workflow the user cannot edit.

## 2. Goals / Non-Goals

### Goals
- Every node kind has a declared, validated configuration schema (n8n-style `properties` array).
- Agent node: dual mode — inherit an existing agent with per-field overrides, or custom inline config (system prompt, model, tools, temperature, max iterations, thinking).
- Scheduler node: visual form generating a real cron expression + IANA timezone.
- Integration node: real Gmail / Google Calendar / Google Drive / webhook data via the existing CI integration stack — no mocks.
- Triager node: real LLM routing (category + reason) and rule-based fallback; edges can route on structured output.
- Tool node: dropdown of registered tools with argument forms/JSON, descriptions, retry/timeout.
- **Structured data-flow**: nodes reference upstream output by key via `input_mapping`.
- **Unified output contract** `{text, data, error}` for every node.
- **Per-node error semantics** `onError: stop|continue|fallback`.
- **Fan-out concurrency limit** (fixed, configurable via settings).
- **Enriched in-editor run view** (single page): KPI strip (status/progress/duration/tokens/cost), per-node trace (timing/tokens/cost/attempts/input/output), canvas status highlight, and a structured event log + replay.
- **Scheduling unification**: editor workflows with a scheduler node fire on the cron tick via a hidden `WorkflowInstallation`.
- Frontend renders node forms dynamically from backend-declared `NodeDefinition`s (single source of truth).
- Backend validates node parameters on save; clear per-node/per-field errors.
- **RBAC: role `user` gets `workflows:create/update/delete` (ownership-scoped). Templates are pre-built workflows the user can install and edit as their own.**

### Non-Goals
- No workflow versioning, sharing, or multi-tenant workflow catalog.
- No visual debugger beyond the enriched in-editor run view + existing console.
- No new integration connectors beyond what exists (Gmail/Calendar/Drive/webhook).
- No expression/template language (`{{node.field}}`); structured `input_mapping` is the mechanism (see §5.6).

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
- This mirrors the existing `PrincipalContext.owner_user_id` pattern (line 96 of `policy.py`): `user_id` when role is `user`, else `None` (meaning no ownership restriction). Reuse `scope_to_owner` (already imported in `workflows.py`) on the update/delete/run read paths.
- `Workflow` model already has `created_by_user_id` (FK users, `workflow.py` line 15) — no schema change needed for ownership.

### Template install → editable workflow

- `POST /api/workflow-catalog/installations` already creates a real `Workflow` row (workflow_id unique) plus a `WorkflowInstallation`. Change the flow so the materialized workflow is **fully editable by the installing user**:
  - The created `Workflow` keeps the template's DAG in `graph` (already seeded via `0050_automation_template_dag_graphs.py`), with `created_by_user_id` = the installing user.
  - The `/automations` UI adds an **"Open in editor"** action on an installed template that navigates to `/workflows?edit=<workflow_id>`.
  - Editing an installed template's workflow updates the DAG but keeps the `WorkflowInstallation` schedule wiring (§5.3) so the user's cron still fires.
- This replaces the current "install creates an opaque workflow" behavior with a transparent, user-owned, editable DAG.

### Permissions on the new endpoints

- `GET /api/workflows/node-definitions`, `GET /api/workflows/node-options`, `GET /api/workflows/tool-options` → require `workflows:read` (user has it).
- Webhook endpoint (§6.2) → unauthenticated (token-verified), as designed.

## 3. Research Summary (patterns from industry tools)

- **n8n** — node configuration is a declarative `properties` array of `INodeProperties` (`displayName`, `name`, `type`, `default`, `description`, `placeholder`, `required`). Types: `string`, `number`, `boolean`, `options`, `multiOptions`, `collection`, `fixedCollection`, `dateTime`, `json`, `resourceLocator`, `notice`, `hidden`. Conditional visibility via `displayOptions.show/hide`. Dynamic dropdowns via `loadOptionsMethod`. Credentials stored separately, encrypted, referenced by id. Resource/Operation pattern. Input/output data flows between nodes as arrays of items, referenced by `$node["name"]` expressions or the Input Mapping UI.
- **Kestra** — triggers are first-class and separate from tasks (`triggers:` vs `tasks:`): schedule, event, webhook.
- **Temporal** — durable execution: activities with retry/heartbeat, signals for human-in-the-loop (matches our approval/resume), durable timers, child workflows (matches `sub_workflow`), Schedules for cron. Workflow-as-code, event-sourcing replay (matches our `ToolCallRecord` replay).
- **Activepieces** — AI-first: each AI node has its own LLM config (model + prompt + temperature); MCP connections supported.

### Applied to this project
- **n8n `properties` → `NodeDefinition.fields`** (declarative, single source of truth; backend validates, frontend renders).
- **n8n Input Mapping → `input_mapping`** (structured data-flow; see §5.6). We deliberately do NOT build the `$node.field` expression engine (YAGNI) — `input_mapping` covers the needed cases.
- **Resource/Operation** for `tool` and `integration` nodes.
- **`displayOptions` → `display`** for conditional fields.
- **`loadOptionsMethod` → `load_options_from`** (tools, models, agents, workflows, connections, users).
- **Kestra-style trigger separation**: scheduler/integration are entry nodes; we unify editor workflows with the Automation Hub scheduler so cron tick fires editor-created workflows with a scheduler node (§5.3).
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
- Frontend `GraphNode` type (`frontend/types/index.ts` line 252) gains optional `parameters?: Record<string, any>`; `config` remains for legacy reads.

### 4.3 Node output contract (unified)

Every node now produces a `NodeOutput`:

```python
class NodeOutput(BaseModel):
    text: str = ""                    # human-readable summary; feeds string concat + logs
    data: dict[str, Any] = {}         # structured payload for downstream input_mapping
    error: str | None = None          # set when onError=continue/fallback produced a soft failure
```

- Internally the engine's `run_node_once` returns `NodeOutput` instead of `str`.
- Persisted to `WorkflowNodeRun.output` as `{"text": ..., "data": ...}` (JSON dict, matching the existing column type; `error` lives on the node run's `error` column).
- `WorkflowRun.output` gains `{"text": final_text, "data": final_data}` where `final_data` is a `{node_id: NodeOutput.data}` map for the run view.

### 4.4 Node parameters per kind (summary)

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

**Common (all nodes)**: `input_mapping` (collection of `{field, source_node_id, source_path}`), `onError` (options: `stop|continue|fallback`), `fallback` (string, when onError=fallback), `retry` (collection `max_attempts`/`backoff_s`), `timeout_s` (number). See §5.6 for semantics.

## 5. Backend Engine Changes

### 5.1 Validation (`workflow_service.py`)

- `validate_graph(graph, org_id)` validates each node's `parameters` against its `NodeDefinition`: required fields, types, allowed options values, valid load_options references (e.g. `model_id` must exist in org).
- Structural validation retained: ≥1 entry node (`input|scheduler|integration`), no cycles (existing DFS), agent custom mode requires `model_id`.
- **New cross-node validation**:
  - `input_mapping` source nodes must exist in the graph and be upstream (topologically reachable to this node); unknown `source_node_id` → error.
  - `sub_workflow` cannot reference itself or form a cycle across workflows (maintain an in-memory chain of workflow ids during validation; a depth cap of 5 sub-workflow nesting).
  - Edge `condition` syntax validated at save time (parse with `simpleeval`; reject on parse error).
  - `output.include=selected` requires `selected_from` non-empty.
- Returns detailed errors: `{node_id, field, message}` list. API surfaces them as `400` with a structured body (see §6.1).

### 5.2 Agent node (`engine.py`)

- **`mode=custom`**: build an in-memory `Agent` (not persisted): `Agent(org_id=..., name=f"workflow-node-{node_id}", system_prompt=..., model_id=..., tools=..., temperature=..., max_iterations=..., enable_thinking=...)`; call `run_agent_loop(agent, text, db, ...)`. The loop already records usage/cost to `Task`/`UsageEvent`; we capture `AgentLoopResult` (`content`, `usage`, `cost_usd`, `latency_ms`, `tool_calls`) into `NodeOutput.data` for the run view.
- **`mode=inherit`**: load `Agent` by `agent_id`; apply each override field onto a shallow copy of the agent object before the loop (system_prompt, model_id, tools, temperature, max_iterations, enable_thinking). Keep `agent_release_id` write on the node run.
- Pass `model_id` through to `run_agent_loop` (already supported).
- No fallback to "first agent in org" when custom mode has no agent — custom mode is self-contained. Inherit mode with no `agent_id` errors clearly.
- Agent node reads its input via `input_mapping` (if present) else falls back to concatenated upstream text (§5.6).

### 5.3 Scheduler node + scheduling unification

- New helper `backend/app/core/workflow/schedule.py`: `build_cron(frequency, time, days_of_week, custom_cron, timezone) -> (cron, schedule_label)`; validates with `croniter`.
- Map `frequency` to the existing `schedule` dict shape consumed by `workflows/scheduler.py::next_run_at` (`kind`, `time`, `weekday`, `interval_hours`), so the existing cron tick needs no change.
- **Unification (single path, decisive)**: when a workflow is saved with a `scheduler` node, `WorkflowService` upserts a hidden `WorkflowInstallation` row:
  - `template_key = "__editor_schedule__"`, `template_version = "0"`, `status = enabled`, `owner_user_id = workflow.created_by_user_id`, `workflow_id = workflow.id`, `schedule` + `timezone` derived from the node.
  - Reuses the existing `run_due_workflows` cron tick unchanged. Editor workflows with a scheduler node fire just like template installations.
  - Removing the scheduler node deletes the hidden installation; editing it updates `schedule`/`timezone`/`next_run_at`.
  - `WorkflowInstallation` already has a partial-unique index on `(org_id, owner_user_id, template_key)` for non-archived rows — we use `template_key="__editor_schedule__"` + a unique `workflow_id` FK to key it; verify the unique constraint allows multiple editor schedules per user (distinct `workflow_id`), and if not, add a migration to relax it.
- Engine's `scheduler` node returns a `NodeOutput` with `text` = `input_text or f"[{label}] Automated trigger initiated (schedule: {cron})."` and `data = {cron, timezone, schedule_label}`.

### 5.4 Integration node — real data

Replace the mock block with real provider calls, scoped to `workflow.org_id` + `actor_user_id`, mirroring `backend/app/customer_intelligence/tools.py` `_connected_*` helpers:

- `gmail`: `EmailConnectionRepository` lookup by `connection_id` (or account) → `load_fresh_credentials` → `McpEmailProvider` (`list_new`/`search`/`get`) → `NodeOutput.data = {"emails": [{from, subject, snippet, date, id}]}`, `text` = a line summary.
- `google_calendar`: `CalendarConnectionRepository.get_connected(org_id, user_id)` → `load_fresh_credentials` → calendar provider `list_events(from, to, max_results)` → `data = {"events": [{title, start_at, end_at, attendees}]}`.
- `google_drive`: `DriveConnectionRepository.get_connected(org_id, user_id)` → `McpDriveProvider.list_files` → `data = {"files": [{name, id, mime_type, modified}]}`.
- `webhook`: read payload from the workflow run input (set by webhook endpoint, §6.2) → `data = {"webhook": payload}`.
- If no connection configured/connected → raise a clear error ("integration node requires a connected Gmail connection; connect one in Settings"); no mock fallback.
- `source` values normalized: accept legacy spellings `google_calendar`/`google_drive` from LLM-generated graphs and map them to canonical `google_calendar`/`google_drive` values used by the UI.

### 5.5 Triager node — LLM routing

- `mode=llm`: build prompt from upstream text + categories + instruction; call LLM via existing `build_driver`/LLM client; parse JSON `{"category": "...", "reason": "..."}` (strict `output_format`). Return `NodeOutput(text=category, data={category, reason})`.
- `mode=rules`: match each rule's regex/keyword against upstream text; first match wins → `NodeOutput(text=category, data={category})`.
- Engine stores `outputs[node_id]`; for edges, support structured conditions: `_eval_condition` extended so `output` may be a `NodeOutput`/dict — conditions like `output.category == "sales"` evaluate against `data`; string conditions evaluate against `text`.
- Keep `urgency_and_intent` default categories for LLM mode when none provided.

### 5.6 Structured data-flow — `input_mapping`

Every node may declare an `input_mapping` (list of `{field, source_node_id, source_path}`):

- `source_node_id`: the upstream node to read from.
- `source_path`: dot path into `NodeOutput.data` (e.g. `emails.0.subject`); empty path means the whole `text`.
- `field`: the key this node reads the mapped value under.

Resolution at runtime (engine, before `run_node_once`):

```python
def resolve_inputs(node, outputs):  # outputs: dict[node_id, NodeOutput]
    if not node.parameters.get("input_mapping"):
        return {"__text__": "\n\n".join(outputs[nid].text for nid in active_upstream)}
    mapped = {}
    for m in node.parameters["input_mapping"]:
        src = outputs[m["source_node_id"]]
        mapped[m["field"]] = _get_path(src.data, m["source_path"]) or src.text
    mapped["__text__"] = "\n\n".join(mapped.values())
    return mapped
```

- Node implementations receive `inputs: dict[str, Any]` (mapped) instead of the current `dict[from_node, str]`.
- Agent node: `text = inputs["__text__"]` or mapped fields assembled into a prompt context block.
- Tool node: mapped fields are merged into tool arguments (plus static `arguments`); a mapped field overrides a static argument of the same name.
- `sub_workflow` node: its `input_mapping` already exists (§4.4); the mapped `__text__` becomes the child workflow's input text.
- Validation: `source_node_id` must exist and be upstream (§5.1).

### 5.7 Per-node error semantics — `onError`

- `onError` values: `stop` (default), `continue`, `fallback`.
- In the scheduling loop, when a node raises:
  - `stop`: mark node `failed`, set `error_flag`, downstream edges of this node are discarded (current behavior).
  - `continue`: mark node `skipped` (new status), record `node_error` event with `"skipped": true`, do NOT set `error_flag`; downstream edges are NOT activated (branch skipped).
  - `fallback`: mark node `succeeded` with output = `NodeOutput(text=parameters["fallback"], data={})`, record `node_error` event with `"fallback": true`; downstream edges activate normally against the fallback text.
- `approval` node and its `WorkflowWaitingApproval` flow are unchanged (pause is not an error).
- Retry (`max_attempts`/`backoff_s`) still applies before `onError` is consulted: `onError` only fires after retries are exhausted.
- `timeout_s` (per node) triggers the same `onError` path.

### 5.8 Fan-out concurrency limit

- New setting `workflow_max_concurrency: int = 8` (`config.py`).
- Replace the unbounded `asyncio.gather` over all ready nodes with a bounded worker pool: use `asyncio.Semaphore(settings.workflow_max_concurrency)` around `run_node_in_new_session`, or chunk ready nodes into batches of `workflow_max_concurrency` per round.
- Ready nodes beyond the limit stay `pending` and are picked up in the next round (the existing `is_ready` loop already re-scans).
- Each node still gets its own DB session (current `async_sessionmaker` fan-out path) — the semaphore only caps concurrency, not correctness.

### 5.9 Edge conditions (extended)

- Extend `_eval_condition(cond, output)` to accept `NodeOutput`:
  - If `cond` references `output.category`/`output.<key>`, evaluate against `output.data`.
  - Else evaluate against `output.text` (string), preserving current string behavior.
- Pre-bind `output.text`, `output.data`, and top-level `output` for backward-compatible string conditions.
- UI offers condition autocomplete (`output.category == "sales"`, `output.text contains "urgent"`, `true`).

### 5.10 Unchanged

Retry/budget/approval/lease/replay/sub_workflow mechanics are retained (retry semantics unified under §5.7).

## 6. API & Webhook Changes

### 6.1 New endpoints

- `GET /api/workflows/node-definitions` → `dict[kind, NodeDefinition]`.
- `GET /api/workflows/tool-options` → list of `{name, description, risk_tier, input_schema?}` for tool dropdowns (from `BUILTIN_TOOLS` + MCP tools + CI tools, scoped to org).
- `GET /api/workflows/node-options?type=models|agents|workflows|connections|users` → dynamic dropdown sources for `load_options_from`.
- `GET /api/workflows/runs` → paginated run list (for the editor run history) with filters `?workflow_id=&status=&limit=&cursor=`.
- `GET /api/workflows/runs/{run_id}` → enriched run detail (see §7.4): run + per-node `{status, attempt, timing_ms, input, output, error, tokens, cost_usd}` + tool call records for the run (for replay inspection).
- `POST /{id}/run` and `POST /{id}` validation errors return a structured `400` body `{"errors": [{node_id, field, message}]}`.

### 6.2 Webhook integration

- New route `POST /api/webhooks/workflow/{workflow_id}/{path}` — unauthenticated, verified by shared token (`workflow_webhook_shared_token` config, mirroring gmail webhook pattern), 1MB body cap.
- On valid request: create `WorkflowRun` (status queued) with `input={"webhook_payload": body, "path": path}` + `WorkflowOccurrence` + outbox event `workflow.run.requested` → worker executes; integration `webhook` node reads `input.webhook_payload`.

## 7. Frontend Changes

### 7.1 Dynamic form renderer

- New `frontend/components/workflows/node-config-form.tsx` — renders fields from `NodeDefinition.fields`:
  - Types: `string` (Input), `textarea` (Textarea, rows from type_options), `number`, `boolean` (Switch), `options` (Select), `multiOptions` (multi-select), `collection` (add-field group), `fixedCollection` (repeatable rows), `json` (JSON editor or textarea with validation).
  - `display`: show/hide per conditions (`{"show": {"mode": ["custom"]}}`).
  - `load_options_from`: fetch via `GET /api/workflows/node-options?type=...` with React Query; refresh on dependent field change.
- `workflow-node-config.tsx` replaced with `NodeConfigForm` + header/delete preserved. Also renders the common `input_mapping`, `onError`, `fallback`, `retry`, `timeout_s` group.
- New hook `useNodeDefinitions()` (key `["workflow-node-definitions"]`).

### 7.2 Types

- `frontend/types/index.ts`: `GraphNode.parameters` added (read fallback to `config`); `NodeField`, `NodeDefinition`, `WorkflowNodeParameters` types; `WorkflowRunDetail` extended with per-node `tokens`/`cost_usd`/`timing_ms`/`data`.

### 7.3 Node-specific UI

- **Agent**: mode toggle (Inherit/Custom); Inherit shows agent dropdown + per-field override checkboxes; Custom shows full inline form.
- **Scheduler**: frequency segmented control, time picker, weekday chips, timezone select, date range; live cron + label preview.
- **Tool**: tool dropdown (with description), arguments JSON editor (schema-aware when tool has `input_schema`), retry/timeout collapsible.
- **Triager**: mode toggle; LLM: categories tag input + instruction + model; Rules: pattern→category table (fixedCollection).
- **Integration**: source dropdown → connections list (with status + Connect button triggering CI OAuth flow) → operation → fields.
- **Input mapping**: a small "Inputs" section on each node listing `{field, source_node_id, source_path}` rows with upstream-node dropdown.
- **Edge**: custom edge click → condition panel with autocomplete + quick category picks from upstream triager.
- **Run page** (`/run-workflow`): input form reflects input node `input_field`/`required`/`description`.

### 7.4 In-editor run view (single page, light-touch)

Keep everything on the existing `/workflows` page; do NOT create a separate route. Enrich the existing editor run experience rather than redesigning it:

- **KPI strip**: a slim status bar that appears above the canvas while a run is active (or when viewing a past run): status pill (queued/running/succeeded/failed/waiting_approval), a thin progress bar (`done/total nodes`), and three mono numbers — duration, total tokens, total cost. Reuses existing `WorkflowRunDetail` + `useWorkflowRun` polling (2s).
- **Canvas status highlight**: `WorkflowCanvas` already receives `nodeStatus`; extend it to render a running-node ring/pulse and color edges that have been traversed. No new canvas library.
- **Node trace**: replace the raw text `WorkflowConsole` log with a two-column panel under the canvas: left = per-node trace (status chip, per-attempt duration, tokens, cost, input/output summary), right = structured event log (timestamp + level + message, filterable by node). Data comes from the enriched `GET /api/workflows/runs/{run_id}`.
- **Replay**: a "Replay" button in the run strip → `POST /api/workflows/runs/{id}/replay`; divergence shown inline.
- The existing `/debug` run inspector reads the same enriched endpoint (no change beyond data shape).

This is a targeted polish of the current editor, not a new surface. No new page, no new route, no `AppShell`/navigation changes for run viewing.

### 7.5 RBAC / navigation

- Template install → editable: `/automations` Active tab gains **"Open in editor"** per installation → `/workflows?edit=<workflow_id>`.
- `/workflows` visible to role `user` (permissions granted); navigation entry no longer gated to operator.

## 8. Migration

- **Data**: `node.config` → `node.parameters` for existing workflows where `parameters` absent (graph is JSON; an in-code backfill on read or a one-off migration script — no `workflows.graph` column change).
- **WorkflowInstallation unique constraint**: verify `(org_id, owner_user_id, template_key)` partial-unique index allows one hidden `__editor_schedule__` installation per user workflow; if it conflicts, add an alembic migration to include `workflow_id` in the uniqueness or relax the constraint.
- **`workflows.schedules`**: not used — scheduling is unified through `WorkflowInstallation` (§5.3).
- Update seeded template DAGs (`0050_automation_template_dag_graphs.py`) to new `parameters` format.
- Update `workflow_service.generate_graph` LLM system prompt to emit `parameters` per the schemas (including `input_mapping`, `onError`).
- New alembic migration: add `workflow_webhook_shared_token` to settings (config-only, no DB column); add index on `workflow_runs(workflow_id, status, started_at)` for the run-list query if missing.

## 9. Testing — four-tier plan

### Tier 1 — Backend unit tests (no I/O, no credentials)

- `test_workflow_node_validation.py`: per-kind required/type/options; cross-node validation (unknown `source_node_id`, `sub_workflow` self/cycle, `output.include=selected` empty, edge condition syntax).
- `test_workflow_schedule.py`: `build_cron` mapping for every `frequency`; `next_run_at` integration with hidden `WorkflowInstallation`.
- `test_workflow_output_contract.py`: every node returns `NodeOutput` with correct `text`/`data`.
- `test_workflow_onerror.py`: `stop`/`continue`/`fallback` branch outcomes (mock nodes).
- `test_workflow_concurrency.py`: fan-out of N>8 ready nodes runs in ≤ ceil(N/8) rounds.
- `test_workflow_eval_condition.py`: string conditions + `output.category`/`output.<key>` against `NodeOutput`.

### Tier 2 — Backend integration tests (mock providers/LLM, in-memory DB)

- `test_workflow_agent_node.py`: custom mode builds ephemeral agent (mock `run_agent_loop`); inherit mode applies overrides; `model_id` passed through.
- `test_workflow_integration_node.py`: gmail/calendar/drive with mocked `EmailConnectionRepository`/`CalendarConnectionRepository`/`DriveConnectionRepository` + provider stubs; missing-connection error; `source` normalization.
- `test_workflow_triager.py`: LLM mode (mock LLM returns JSON) + rules mode (regex/keyword).
- `test_workflow_input_mapping.py`: mapping resolution + tool args merge + sub_workflow mapped input.
- `test_workflow_rbac.py`: user create/update/delete own; 403 on other's; operator/org_admin unaffected; install template then edit materialized workflow; run own + published.
- `test_workflow_webhook.py`: token auth (valid/invalid), run creation, outbox event, payload into integration node.

### Tier 3 — Frontend component + E2E (Playwright)

- Component: `node-config-form` renders per definition; `display` logic; `load_options` fetch; input-mapping editor.
- E2E (Playwright, against mock backend or with provider/LLM stubbed): create a workflow with custom agent + scheduler + tool via UI → save → run → assert the in-editor run view (KPI strip, per-node trace, event log, canvas highlight). Assert a `user` role can create/edit/delete own workflow and open an installed template in the editor.

### Tier 4 — Live smoke test (manual, optional, requires real credentials)

- With a real Google connection (dev org) + a real LLM: install `gmail_monitor_and_triage`, run, verify real emails are fetched and triaged; create a scheduler workflow, verify it fires on the cron tick; open the in-editor run view and confirm token/cost are non-zero.

### Test command baseline

- Backend: `pytest -q` under `backend/` (matches README).
- Frontend: `npm run typecheck && npm run build` under `frontend/`; Playwright suite per project convention.
- All automated tiers (1–3) run with no real credentials; tier 4 is a documented manual checklist.

## 10. Implementation Order

1. Backend: `NodeDefinition`/`NodeField` + `node_definitions.py` + `GET /api/workflows/node-definitions` + `node-options` + `tool-options` + validation in `workflow_service`.
2. **RBAC**: grant `workflows:create/update/delete` to `user`; ownership-scoped enforcement on update/delete; un-gate `/workflows` UI.
3. Backend engine: `NodeOutput` contract; agent custom/inherit; scheduler cron helper + hidden `WorkflowInstallation` unification; integration real providers; triager LLM/rules; `input_mapping` resolution; `onError` semantics; fan-out semaphore; `_eval_condition` dict.
4. Migration: backfill `config` → `parameters`, `WorkflowInstallation` constraint check, update seeded templates, update LLM generation prompt, run-list index.
5. Frontend: `NodeConfigForm` + types + hook; replace hardcoded config; per-node UI; input-mapping editor; edge condition panel; in-editor run view (KPI strip + node trace + event log + canvas highlight); run page input form; "Open in editor" on installed templates.
6. Webhook endpoint + run-list endpoint.
7. Tests (Tier 1–3) + typecheck/build; document Tier 4 manual checklist.

## 11. Risks / Open Items

- **Real Google API in tests**: integration node tests must mock providers; no live credentials in CI (Tier 4 is manual).
- **`croniter` dependency**: confirm it is already available (used by scheduler) or add it.
- **Backward compatibility**: old workflows with `config` must still run (read fallback); write path normalizes to `parameters`.
- **`WorkflowInstallation` unique constraint** for `__editor_schedule__`: verify and migrate if needed (§8).
- **LLM triager cost**: LLM routing runs per execution; budget tracker already caps cost — document that triager LLM calls count toward node budget.
- **Fan-out semaphore vs lease heartbeat**: batching rounds must still call `resume.extend_lease` between rounds (§5.8), so a long fan-out does not look abandoned.
