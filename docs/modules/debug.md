# Module: Debug

## Purpose
Make the agent **inspectable**. Instead of scattered logs, one surface exposes
raw messages, tool calls, token usage, latency, and cost for any session — plus
global usage analytics.

## Data Model
- `messages` (`database-schema.md §2.8`): `meta` JSON carries
  `{ model, in_tokens, out_tokens, cost_usd, latency_ms, compacted }`.
- `usage_events` (`§2.9`): per-call metering rows.

## API
| Method | Path | Returns |
|--------|------|---------|
| GET | `/api/debug/sessions/{id}` | `DebugSession` |
| GET | `/api/usage` | `UsageSummary` (totals + per-agent) |
| GET | `/api/usage/agents/{id}` | `UsageSummary` (one agent) |
| GET | `/api/health` | `{status, version}` |

### `DebugSession`
```json
{ "session_id":"uuid", "agent":{...}, "messages":[
    {"role":"user","content":"...","tool_calls":null,"meta":null},
    {"role":"assistant","content":"","tool_calls":[{"id":"c1","name":"web_fetch","args":{...}}],
     "meta":{"model":"gpt-4o-mini","in_tokens":300,"out_tokens":20,"cost_usd":0.0001,"latency_ms":820}},
    {"role":"tool","tool_call_id":"c1","content":"...fetched...","meta":null}
  ],
  "usage_total":{"in_tokens":...,"out_tokens":...,"cost_usd":...} }
```

### `UsageSummary`
```json
{ "total": {"in_tokens":...,"out_tokens":...,"cost_usd":...},
  "per_agent": [ {"agent_id":"uuid","name":"researcher","cost_usd":0.12}, ... ] }
```

## Behavior
- `debug_service` reads sessions + messages (with `meta`) and aggregates
  `usage_events` (group by agent, sum tokens/cost).
- No writes — read-only observability.

## Layers
- `routes/debug.py` — thin read endpoints.
- `services/debug_service.py` — assembly + aggregation.
- `repositories/session_repo.py`, `usage_repo` (within session_repo or own).

## Frontend
- `app/debug/page.tsx`: session picker + usage dashboard.
- `components/debug/session-tree.tsx`: expandable message tree (role color,
  tool_call/result cards, per-turn `meta` badge: model · tokens · $ · ms).
- `components/debug/usage-chart.tsx`: per-agent cost bars (simple CSS bars or a
  tiny chart lib).
- `hooks/useDebug.ts`: `useDebugSession(id)`, `useUsage()`.

## Notes
- When `OPENAGENT_LOG_LEVEL=DEBUG`, `core/llm.py` can also attach raw request/
  response to `meta` (or a separate `debug raw` toggle) for deep inspection.
- This replaces OpenFang's distributed logging with one queryable surface —
  essential for a personal multi-agent system you actually trust.
