# Module: MCP

## Purpose
Let agents use tools hosted by external **MCP** (Model Context Protocol)
servers. OpenAgent is an MCP **client**: it connects, lists tools, and proxies
tool calls. Connected tools appear as `mcp:<server>:<tool>` in the agent tool
picker.

## Data Model
- `mcp_servers` (`database-schema.md §2.4`): `name`, `transport`
  (`stdio|sse|http`), `command`/`args` (stdio), `url` (sse/http), `env` (names
  only), `enabled`, `connected`.
- `mcp_tools` (`§2.5`): discovered tools per server (`tool_name`,
  `description`, `input_schema` JSON, `granted`).

## API
| Method | Path | Body | Returns |
|--------|------|------|---------|
| GET | `/api/mcp` | — | list servers (+ tool counts) |
| POST | `/api/mcp` | `McpServerCreate` | created |
| GET/PUT/DELETE | `/api/mcp/{id}` | `McpServerUpdate` | one (with tools) |
| POST | `/api/mcp/{id}/connect` | — | `{ok, tools:[McpTool]}` |
| POST | `/api/mcp/{id}/disconnect` | — | 204 |

## Behavior
- **Connect**: open a connection via `mcp/client.py` (stdio spawns the command;
  sse/http open the stream). Call `list_tools()`, persist `mcp_tools`, mark
  `connected=true`. Keep the live `MCPConnection` in an in-memory registry
  keyed by server name (lost on restart — re-connect on boot or on first use).
- **Disconnect**: close the connection, `connected=false`.
- **Tool execution**: `core/tools` registers `mcp:<server>:<tool>` entries that
  delegate to `MCPConnection.call(tool, args)` and return text. Failures return
  an error string (model-recoverable).
- **Env**: only variable **names** are stored; values are injected from the
  process environment at connect time (never persisted).

## Layers
- `routes/mcp.py` — validate, call service.
- `services/mcp_service.py` — connect/disconnect orchestration, tool persistence.
- `repositories/mcp_repo.py` — servers + tools CRUD.
- `mcp/client.py` — `MCPConnection` wrapper over the `mcp` SDK.

## Frontend
- `app/mcp/page.tsx`: server cards with connect/disconnect toggle, tool list.
- `components/mcp/mcp-form.tsx`: transport switch (stdio vs sse/http) →
  conditional fields. Zod discriminated union on `transport`.
- `hooks/useMcp.ts`: list, create, `useConnectMcp` (mutation → toast + refresh).
- After connect, agents' tool multi-select auto-includes `mcp:*` entries.

## Notes
- A tool disabled in `mcp_tools.granted=false` is hidden from agents.
- Connection lifetime: in-memory for v1. For resilience, reconnect lazily when a
  tool is invoked and the connection is down.
