# Module: Chat

## Purpose
Talk to an agent (or resume a session). Streaming, tool-call visibility, and
per-turn cost. One session = one agent in v1.

## Data Model
- `sessions` (`database-schema.md §2.7`): `agent_id`, `title`, `status`.
- `messages` (`§2.8`): `role`, `content`, `tool_calls` (JSON), `tool_call_id`,
  `meta` (model, tokens, cost, latency), `seq`.

## API
| Method | Path | Body | Returns |
|--------|------|------|---------|
| POST | `/api/agents/{id}/message` | `ChatMessage` | `AgentLoopResult` / SSE |
| POST | `/api/sessions/{id}/message` | `ChatMessage` | `AgentLoopResult` / SSE |
| GET | `/api/sessions` | `?agent_id=` | list |
| POST | `/api/sessions` | `{agent_id,title}` | created |
| GET | `/api/sessions/{id}/messages` | — | history |
| DELETE | `/api/sessions/{id}` | — | 204 |

`ChatMessage`:
```json
{ "session_id": "uuid|null", "message": "Summarize this PDF",
  "attachments": ["/workspace/report.pdf"], "stream": true }
```

## Behavior (chat_service → agent_loop)
1. `session_repo.load_or_create(session_id, agent_id)`.
2. If total tokens > `0.8 * model.context_window` → `compactor.compact(session)`
   (see `compactor.md`); keep a compacted snapshot, preserve recent N messages.
3. Append user message (with attachment references).
4. `agent_loop.run(agent, history, tools, llm_client)`:
   - loop ≤ `agent.max_iterations`:
     - `llm.chat(system, history, tool_schemas)` → response
     - if no `tool_calls` → break
     - for each call: capability gate → `tool.execute(args, ctx)` → append result
   - accumulate `usage`.
5. Persist messages + `usage_events`.
6. Return/stream `AgentLoopResult`.

## Streaming & durability (event-sourced run)
`POST /api/chat` (`stream:true`) no longer returns the agent's token/tool
frames over the HTTP response. The POST only creates a durable `Task` (the
run) and returns two bootstrap frames — `session_start`, `chat_run_start` —
so the client learns the `run_id` and `session_id` immediately, then the agent
loop runs in a background task / arq worker.

Every frame the loop emits is also appended to a durable event log
(`chat_run_events`, per `run_id`, monotonic `seq`). A client that reloads the
page mid-run reconnects via `GET /api/chat/runs/{run_id}/events?follow=true`
which **drains the log and rebuilds the exact UI** (partial assistant text,
reasoning in progress, running tool cards, live tool progress) and then keeps
following new frames until a terminal event. `follow=false` returns the log
as a JSON snapshot. This makes in-flight chat state survivable across reloads
and tab switches, not just the final transcript.

Event vocabulary (idempotent / replayable):
```
message_start | reasoning* | token* | tool_call_delta* | tool_call |
tool_progress* | tool_result | retry | self_correct | message_done |
error | approval_required | budget_exceeded | replay_diverged
```

`GET /api/chat/runs/{run_id}` additionally returns a `progress` checkpoint
(`phase`, `last_seq`, `content_chars`, …) updated by the loop, so a polling
client can show "Using tool X…" without touching the event log, and the
worker's orphan sweep can tell a live run from a dead one.

> A chat `Task` stuck `running`/`queued` with no progress heartbeat for
> ~2 min is failed by the worker cron (`worker.py::_fail_orphaned_chat_runs`)
> with reason "worker lost", so the UI never spins forever.

## Attachments
`attachments` are local workspace paths. The first tool the model typically uses
is `read_attachment` to pull their content. (Frontend uploads TBD; v1 passes
paths.) `safe_path()` confines them to the workspace.

## Layers
- `routes/chat.py` — parse `ChatMessage`, choose SSE vs JSON, call service.
- `services/chat_service.py` — session mgmt, compaction trigger, loop orchestration.
- `repositories/session_repo.py` — messages CRUD, ordering.
- `core/agent_loop.py`, `core/llm.py` — execution.

## Frontend
- `app/chat/page.tsx`: agent `<Select>`, session list, message thread.
- `components/chat/chat-window.tsx`: renders roles; tool_call/tool_result as
  collapsible cards; streaming via `EventSource`/fetch-stream + TanStack Query.
- `components/chat/composer.tsx`: textarea + send; shows latency + cost per turn
  (from `meta`).
- `stores/chat-store.ts`: current session, draft, streaming buffer.
- `hooks/useChat.ts`: `useSessions`, `useSendMessage` (SSE consumer).

## Notes
- Latency (`meta.latency_ms`) and `cost_usd` come straight from `core/llm.py`.
- The same `agent_loop.run` powers both chat and `call_agent` delegation and
  workflow `agent` nodes — one engine, three entry points.
