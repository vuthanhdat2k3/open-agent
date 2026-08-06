# OpenAgent — API Reference

All endpoints are under `/api`. Request/response bodies are JSON unless noted.
Streaming endpoints return `text/event-stream` (SSE). Auth: Bearer token in
`Authorization` header when `OPENAGENT_API_KEY` is set; loopback-only when empty.

> Schema names below map 1:1 to `app/schemas/*.py` (Pydantic) and
> `frontend/lib/schemas.ts` (Zod).

---

## Conventions

- Errors: `{ "error": { "code": "NOT_FOUND", "message": "..." } }` with appropriate
  HTTP status (400/401/404/422/500).
- IDs are UUID strings.
- Timestamps: ISO-8601 UTC.
- Pagination (list endpoints): `?limit=50&offset=0` → `{ "items": [...], "total": N }`.

---

## 1. Providers

| Method | Path | Body | Returns |
|--------|------|------|---------|
| GET | `/api/providers` | — | `ProviderList` |
| POST | `/api/providers` | `ProviderCreate` | `Provider` |
| GET | `/api/providers/{id}` | — | `Provider` |
| PUT | `/api/providers/{id}` | `ProviderUpdate` | `Provider` |
| DELETE | `/api/providers/{id}` | — | `204` |
| POST | `/api/providers/{id}/test` | — | `{ "ok": true, "models": [...] }` |

**ProviderCreate**
```json
{ "name": "groq", "base_url": "https://api.groq.com/openai/v1", "api_key_env": "GROQ_API_KEY" }
```
**Provider** (response)
```json
{ "id": "uuid", "name": "groq", "base_url": "...", "api_key_env": "GROQ_API_KEY",
  "is_default": false, "created_at": "2026-07-14T10:00:00Z", "updated_at": "..." }
```

---

## 2. Models

| Method | Path | Body | Returns |
|--------|------|------|---------|
| GET | `/api/models` | query: `?provider=&tier=&with_inactive=` | `ModelList` |
| POST | `/api/models` | `ModelCreate` | `Model` |
| GET | `/api/models/{id}` | — | `Model` |
| PUT | `/api/models/{id}` | `ModelUpdate` | `Model` |
| DELETE | `/api/models/{id}` | — | `204` |

**ModelCreate**
```json
{ "provider_id": "uuid", "name": "llama-3.3-70b", "display_name": "Llama 70B",
  "tier": "fast", "context_window": 131072,
  "input_cost_per_1k": 0.0005, "output_cost_per_1k": 0.0008, "active": true }
```
**Model** (response)
```json
{ "id": "uuid", "provider_id": "uuid", "name": "llama-3.3-70b",
  "display_name": "Llama 70B", "tier": "fast", "context_window": 131072,
  "input_cost_per_1k": 0.0005, "output_cost_per_1k": 0.0008, "active": true,
  "created_at": "..." }
```

---

## 3. Agents

| Method | Path | Body | Returns |
|--------|------|------|---------|
| GET | `/api/agents` | — | `AgentList` |
| POST | `/api/agents` | `AgentCreate` | `Agent` |
| GET | `/api/agents/{id}` | — | `Agent` |
| PUT | `/api/agents/{id}` | `AgentUpdate` | `Agent` |
| DELETE | `/api/agents/{id}` | — | `204` |
| GET | `/api/agents/{id}/tools` | — | `{ "tools": [ToolInfo] }` (builtin + mcp) |

**AgentCreate**
```json
{ "name": "researcher", "description": "Deep researcher",
  "system_prompt": "You are a careful researcher...",
  "model_id": "uuid",
  "tools": ["read_attachment", "call_agent", "web_fetch", "memory_store", "memory_recall"],
  "max_iterations": 12, "temperature": 0.7 }
```
**Agent** (response)
```json
{ "id": "uuid", "name": "researcher", "description": "...",
  "system_prompt": "...", "model_id": "uuid",
  "tools": ["read_attachment","call_agent","web_fetch","memory_store","memory_recall"],
  "max_iterations": 12, "temperature": 0.7,
  "created_at": "...", "updated_at": "..." }
```

---

## 4. MCP

| Method | Path | Body | Returns |
|--------|------|------|---------|
| GET | `/api/mcp` | — | `McpServerList` |
| POST | `/api/mcp` | `McpServerCreate` | `McpServer` |
| GET | `/api/mcp/{id}` | — | `McpServer` (with tools) |
| PUT | `/api/mcp/{id}` | `McpServerUpdate` | `McpServer` |
| DELETE | `/api/mcp/{id}` | — | `204` |
| POST | `/api/mcp/{id}/connect` | — | `{ "ok": true, "tools": [McpTool] }` |
| POST | `/api/mcp/{id}/disconnect` | — | `204` |

**McpServerCreate** (stdio example)
```json
{ "name": "rag", "transport": "stdio", "command": "python",
  "args": ["-m","rag_server"], "env": {"PYTHONPATH": "/srv/rag"}, "enabled": true }
```
**McpTool**
```json
{ "id": "uuid", "server_id": "uuid", "tool_name": "search",
  "description": "Semantic search", "input_schema": { /* json schema */ },
  "granted": true }
```

---

## 5. Workflows (multi-agent graph)

| Method | Path | Body | Returns |
|--------|------|------|---------|
| GET | `/api/workflows` | — | `WorkflowList` |
| POST | `/api/workflows` | `WorkflowCreate` | `Workflow` |
| GET | `/api/workflows/{id}` | — | `Workflow` |
| PUT | `/api/workflows/{id}` | `WorkflowUpdate` | `Workflow` |
| DELETE | `/api/workflows/{id}` | — | `204` |
| POST | `/api/workflows/{id}/run` | `WorkflowRunRequest` | `WorkflowRun` (SSE if `stream`) |

**Graph JSON shape**
```json
{
  "nodes": [
    { "id": "n1", "kind": "input", "config": { "inputs": { "topic": "AI agents" } } },
    { "id": "n2", "kind": "agent", "ref": "agent_id_or_name", "config": {} },
    { "id": "n3", "kind": "agent", "ref": "writer", "config": {} },
    { "id": "n4", "kind": "merge", "config": { "mode": "concat" } },
    { "id": "n5", "kind": "output", "config": {} }
  ],
  "edges": [
    { "from": "n1", "to": "n2" },
    { "from": "n1", "to": "n3" },
    { "from": "n2", "to": "n4" },
    { "from": "n3", "to": "n4" },
    { "from": "n4", "to": "n5" }
  ]
}
```
**WorkflowRunRequest**
```json
{ "inputs": { "topic": "optional override" }, "stream": true }
```
**SSE events** (`event:` lines)
```
event: node_started   data: {"node_id":"n2","kind":"agent"}
event: node_completed data: {"node_id":"n2","output":"...","usage":{...}}
event: workflow_done  data: {"outputs":{"n5":"final result"},"usage_total":{...}}
event: error          data: {"node_id":"n2","message":"..."}
```

---

## 6. Chat

| Method | Path | Body | Returns |
|--------|------|------|---------|
| GET | `/api/sessions` | query `?agent_id=` | `SessionList` |
| POST | `/api/sessions` | `{ "agent_id": "uuid", "title": "..." }` | `Session` |
| GET | `/api/sessions/{id}/messages` | — | `MessageList` |
| POST | `/api/chat` | `ChatMessage` (`stream:true`) | durable `Task` + 2 bootstrap SSE frames (`session_start`, `chat_run_start`) |
| GET | `/api/chat/runs/{run_id}` | — | run status + `progress` checkpoint (phase, last_seq, counters) |
| GET | `/api/chat/runs/{run_id}/events?follow=<bool>&after_seq=<int>` | — | durable event log (see below) |
| DELETE | `/api/sessions/{id}` | — | `204` |

**ChatMessage**
```json
{ "session_id": "uuid|null", "run_id": "uuid|null", "message": "Summarize this PDF",
  "model_id": "uuid|null", "attachments": ["/workspace/report.pdf"], "stream": true }
```
**SSE frames** for `stream:true` (live POST only bootstraps the run):
```
event: session_start   data: {"session_id":"uuid"}
event: chat_run_start  data: {"run_id":"uuid","session_id":"uuid","status":"running|queued"}
```
The agent loop itself runs in a background task / arq worker and emits a
**durable event log** (`chat_run_events`) instead of an SSE the browser holds.
To render or recover a run the client opens
`GET /api/chat/runs/{run_id}/events?follow=true` — it drains every recorded
frame (rebuild partial text, reasoning, running tool cards, live progress) and
then follows new frames until a terminal event. `follow=false` returns a
one-shot JSON snapshot (`{run_id, status, events:[{seq,event,data}]}`).

Full event vocabulary (idempotent — safe to replay):
```
message_start | reasoning* | token* | tool_call_delta* | tool_call |
tool_progress* | tool_result | retry | self_correct | message_done |
error | approval_required | budget_exceeded | replay_diverged
```
Each event's `data` carries a `seq` (monotonic per run) so a reconnect can
resume from `after_seq`.

---

## 7. Debug

| Method | Path | Returns |
|--------|------|---------|
| GET | `/api/debug/sessions/{id}` | `DebugSession` (raw messages + tool calls + usage) |
| GET | `/api/usage` | `UsageSummary` (totals + per-agent) |
| GET | `/api/usage/agents/{id}` | `UsageSummary` for one agent |
| GET | `/api/health` | `{ "status":"ok","version":"0.1.0" }` |

**DebugSession**
```json
{ "session_id": "uuid", "agent": {...}, "messages": [
    { "role":"user", "content":"...", "meta":null },
    { "role":"assistant", "content":"", "tool_calls":[{"id":"c1","name":"web_fetch","args":{...}}],
      "meta": { "model":"gpt-4o-mini","in_tokens":300,"out_tokens":20,"cost_usd":0.0001,"latency_ms":820 } },
    { "role":"tool", "tool_call_id":"c1", "content":"...fetched text...", "meta":null }
  ], "usage_total": { "in_tokens":..., "out_tokens":..., "cost_usd":... } }
```

---

## 8. OpenAI-compatible (optional)

Mirrors OpenAI so external tools can point at OpenAgent.

| Method | Path | Notes |
|--------|------|-------|
| POST | `/v1/chat/completions` | `model` = agent id/name or model id; `stream` supported. |
| GET | `/v1/models` | Lists agents + models as OpenAI model objects. |

---

## 9. Frontend ↔ Backend Contract

- Frontend calls `/api/*` (proxied in dev via `next.config.mjs` rewrites to
  `:8000`). In prod, serve Next static + put API behind same origin / reverse proxy.
- TanStack Query hooks wrap these endpoints; Zod schemas validate responses.
- Zustand stores hold UI state (selected agent, workflow graph being edited,
  chat draft).
