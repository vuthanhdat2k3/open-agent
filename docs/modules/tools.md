# Module: Tools

## Purpose
The **tool system** is what turns an LLM into an agent. Tools are functions the
model can call. OpenAgent ships builtins and proxies MCP tools. Every tool runs
behind a **capability gate** (only granted tools are executable).

## Tool Contract
```python
class Tool:
    id: str                       # e.g. "read_attachment", "mcp:rag:search"
    description: str              # shown to the LLM
    parameters_json_schema: dict  # JSON schema for args
    async def execute(args: dict, ctx: ToolContext) -> str: ...
```
`ToolContext` carries: `session_id`, `agent_id`, `workspace_dir`,
`mcp_connections: dict[str, MCPConnection]`, `depth: int`, and a `log` callback.

## Built-in Tools

| id | args | behavior |
|----|------|----------|
| `read_attachment` | `{ "path": str }` | Read a text file **inside workspace**. `paths.safe_resolve()` rejects `..` and absolute escapes. Returns text (truncated 50k chars). |
| `write_file` | `{ "path": str, "content": str }` | Write text to a file **inside workspace** (creates parent dirs). Sandboxed via `paths.safe_resolve()`. |
| `list_dir` | `{ "path": str }` (optional) | List files/dirs **inside workspace**. Defaults to workspace root. |
| `search_files` | `{ "pattern": str, "glob"?: str, "max_results"?: int }` | Regex search over workspace file contents; `glob` filters files (e.g. `*.py`). Skips binaries/large dirs. |
| `call_agent` | `{ "target_agent_id": str, "instruction": str }` | Resolve target agent by id, run via `run_agent_loop()` with the instruction, return final text. `depth+1`; abort if `depth > MAX_AGENT_DEPTH`. |
| `web_fetch` | `{ "url": str }` | `httpx` GET; returns text (truncated 50k chars). |
| `web_search` | `{ "query": str, "max_results"?: int }` | Keyless web search (DuckDuckGo HTML); returns title/url/snippet list. |
| `run_shell` | `{ "cmd": str, "cwd"?: str, "timeout"?: number }` | **DANGEROUS.** Execute a shell command in the workspace; returns output + exit code. Only grant to trusted agents. |
| `memory_store` | `{ "key": str, "value": str }` | Persist KV in the in-memory agent store (v1). |
| `memory_recall` | `{ "key": str }` | Recall a value stored via `memory_store`. |
| `save_memory` | `{ "key": str, "value": str }` | Save a **user-profile** fact (name, preferences, context) so it survives across turns; stored in a separate user namespace. |
| `call_memory` | `{ "query"?: str, "key"?: str }` | Recall user-profile facts. Keyword search via `query`; exact lookup via `key`; omit both to list everything remembered about the user. |
| `mcp:<server>:<tool>` | tool-defined | Proxied to `MCPConnection.call(tool, args)`; see `mcp.md`. |

## Capability Gate (security)
`core/security.py`:
- The agent loop builds the **allowed set** from `agent.tools`.
- Before executing, `registry.get(name)` must exist **and** be in the allowed
  set. Unknown/ungranted → returns `"permission denied: <tool>"` to the LLM
  (no exception, so the model can recover).
- `safe_path()` confines file reads to `workspace_dir`.
- `safe_url()` implements SSRF-lite (block `file://`, private ranges, cloud
  metadata `169.254.169.254`).

## Loop Guard
`core/agent_loop.py` tracks `(tool, sha256(args))` counts:
- warn at `OPENAGENT_LOOP_WARN` (3), block at `OPENAGENT_LOOP_BLOCK` (5),
  circuit-break the whole loop at `OPENAGENT_LOOP_CIRCUIT` (30). Mirrors
  OpenFang's LoopGuard, prevents runaway tool loops.

## Registry
`core/tools/registry.py` holds builtins + dynamically-registered MCP tools
(keyed `mcp:<server>:<tool>`). `agent_loop` resolves the agent's `tools` list
against the registry at run time.

## Layers
- `core/tools/*` — implementations (no HTTP).
- `core/agent_loop.py` — drives the loop, applies gate + guard.
- `routes/agents.py#/tools` — exposes the catalog to the UI.

## Frontend
- Tool metadata (id, description, JSON schema) drives the agent "tools"
  multi-select and, for `call_agent`, an agent picker; for `mcp:*` tools, they
  appear automatically once an MCP server is connected.
- `lib/schemas.ts` includes a `ToolInfo` Zod type (mirrors `AgentTools` response).
