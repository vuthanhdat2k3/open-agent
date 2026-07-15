# Module: Agents

## Purpose
An **Agent** binds a `system_prompt`, a `model`, and a **granted tool set** into
a reusable autonomous unit. Agents are the atoms of chat and of workflow nodes.
An agent can also delegate to another agent via the `call_agent` tool.

## Data Model
See `database-schema.md §2.3 agents`. Key fields:
- `name` (unique), `description`, `system_prompt`, `model_id` (FK→models),
  `tools` (JSON list of granted tool ids), `max_iterations`, `temperature`.

`tools` example:
```json
["read_attachment","call_agent","web_fetch","memory_store","memory_recall","mcp:rag:search"]
```
Only tools in this list are visible to the LLM; the agent loop rejects anything else.

## API
| Method | Path | Body | Returns |
|--------|------|------|---------|
| GET | `/api/agents` | — | list |
| POST | `/api/agents` | `AgentCreate` | created |
| GET/PUT/DELETE | `/api/agents/{id}` | `AgentUpdate` | one |
| GET | `/api/agents/{id}/tools` | — | available tools (builtin + mcp) |

## Behavior
- **Create/Update**: validate `model_id` exists; validate each `tools` entry is
  a known builtin (`read_attachment`, `call_agent`, `web_fetch`, `memory_store`,
  `memory_recall`) or an `mcp:<server>:<tool>` id present in `mcp_tools`.
- **Run**: delegated to `core/agent_loop.py` (see `chat.md` / `tools.md`).
- **`/tools`**: returns the tool catalog for the agent builder UI — builtins
  (static) plus currently-connected MCP tools, with descriptions + JSON schemas.

## Layers
- `routes/agents.py` — validate `AgentCreate`/`AgentUpdate`.
- `services/agent_service.py` — validation, tool resolution, load-by-id/name.
- `repositories/agent_repo.py` — CRUD.

## Frontend
- `app/agents/page.tsx`: cards/list of agents, edit + delete.
- `components/agents/agent-form.tsx`:
  - `system_prompt` → shadcn `Textarea` (mono).
  - `model_id` → `<Select>` populated from `useModels`.
  - `tools` → multi-select (`Command` + `Popover` or `MultiSelect`) of available
    tools from `useAgentTools(id)`.
  - `max_iterations`, `temperature` → `Slider` / `Input`.
- `hooks/useAgents.ts`, `hooks/useAgentTools.ts`.
- Zod schema mirrors `AgentCreate` (tools: `z.array(z.string())`).

## Notes
- Naming: keep `name` stable; it is also usable as a `call_agent` target
  (`ref` in workflows). `resolve_agent(ref)` accepts id or name.
- Recursive delegation depth is capped (`OPENAGENT_MAX_AGENT_DEPTH=5`) in
  `core/tools/call_agent.py`.
