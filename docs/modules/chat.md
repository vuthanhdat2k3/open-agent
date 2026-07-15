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

## Streaming (SSE)
`stream:true` → `text/event-stream`:
```
event: token       data: {"delta":"Here "}
event: token       data: {"delta":"is the "}
event: tool_call   data: {"name":"read_attachment","args":{...}}
event: tool_result data: {"name":"read_attachment","result":"..."}
event: done        data: {"response":"...","usage":{...}}
```

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
