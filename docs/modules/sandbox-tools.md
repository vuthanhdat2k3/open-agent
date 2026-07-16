# Sandbox Tools & Agent Self-Correction

This module documents the agent's local-file toolset, the Docker-isolated code
execution tool (`run_code`), the `workspace/` jail, and the agent-loop
self-correction behavior.

> Plan of record: `.omo/plans/local-files-sandbox-agentloop.md`.

## 1. Overview

Agents call tools the same way as before: the LLM emits `tool_calls`, the runtime
executes each via `ToolSpec.run(args, ToolContext)` and feeds the result back. Three
capability groups exist:

| Group | Tools | Isolation | Status |
|-------|-------|-----------|--------|
| Local files | `read_attachment`, `write_file`, `list_dir`, `search_files` | Jailed to `workspace/` | Shipped |
| Shell | `run_shell` | **Host subprocess** (not isolated) | Shipped |
| Sandbox code | `run_code` | **Docker container** (`docker run --rm`) | New |

## 2. The `workspace/` jail

Every filesystem tool resolves paths through `app.core.tools.paths.safe_resolve`:

```python
base = os.path.abspath(workspace_dir)
target = os.path.abspath(os.path.join(base, path))
if target != base and not target.startswith(base + os.sep):
    return None   # rejected
```

- Relative paths are joined to `workspace_dir` (default `./workspace`, from
  `Settings.workspace_dir`).
- `..` traversal and absolute paths (e.g. `/etc/passwd`) are rejected → the tool
  returns `error: path escapes workspace directory`.
- `ToolContext.workspace_dir` carries the active root; the loop sets it from
  `settings.workspace_dir`.

## 3. Tool reference

### `read_attachment`
Read a text file. `{ "path": "<rel>" }` → file contents (truncated at 50k chars).

### `write_file`
Write text, creating parent dirs. `{ "path": "<rel>", "content": "..." }`
→ `wrote N chars to <path>`.

### `list_dir`
List a directory. `{ "path": "<rel>" (optional, default ".") }`
→ `[dir]`/`[file]` entries (max 500).

### `search_files`
Regex content search. `{ "pattern": "regex", "glob": "**/*" (opt),
"max_results": 200 (opt) }` → `rel:line: text` hits. Skips `.git`, `node_modules`,
`__pycache__`, binary extensions.

### `run_shell` (host — not isolated)
Execute a shell command **on the backend host**. `{ "cmd", "cwd" (opt, in workspace),
"timeout" (opt, default 30) }` → combined output + `[exit code: N]`.
Marked DANGEROUS; grant only to trusted agents. Use `run_code` when isolation is needed.

### `run_code` (Docker sandbox — new)
Execute Python or bash inside a throwaway container.

Inputs:
```json
{
  "language": "python | bash",
  "code": "print(sorted([3,1,2]))",
  "filename": "script.py (optional)",
  "timeout": 30.0 (optional)
}
```

Runtime:
1. Create `workspace/.sandbox/<uuid>/`, write `filename` with `code`.
2. `docker run --rm --network none --memory=256m --cpus=1.0 \
     -v "<abs tempdir>:/work:rw" -w /work \
     <image> <cmd> <filename>`
   - python → image `python:3.11-slim`, cmd `python`
   - bash   → image `bash:5`, cmd `bash`
3. Capture stdout/stderr + exit code; truncate at 50k.
4. `shutil.rmtree(tempdir)` (best-effort).

Outputs:
- Success: `<stdout>\n[exit code: 0]`
- Failure: `<stdout/stderr>\n[exit code: N]` (non-zero), or
  `error: <reason>` for infra failures (timeout, docker unavailable, image missing).

### Docker-unavailable behavior
If the Docker daemon/cli is missing, `run_code` returns
`error: docker unavailable — sandbox execution requires a running Docker daemon`
and the agent loop continues (no 500). The availability is probed once at module
load (`docker info`) and cached.

## 4. Agent-loop self-correction

The loop (`core/agent_loop.py`) already re-prompts after each tool result. Self-
correction adds **error detection + bounded retry**:

1. After a tool step, each `tool_result` is inspected. A result is a *failure* if it:
   - starts with `error:`, or
   - (for `run_code`/`run_shell`) reports a non-zero exit code, or
   - matches a known exception signature.
2. On failure, the loop appends a directive before the next LLM call:
   `The previous tool '<name>' failed. Error: <result>. Analyze, fix, and retry.`
3. `consecutive_failures` increments per failure and **resets to 0** on any success.
4. When `consecutive_failures >= max_retries` (default 3), the loop trips a
   **circuit breaker**: emits `self_correct` (`status: "circuit_breaker"`) with the
   final error and lets the model produce a final answer (or an `error` event).

### Budget
- Each retry is one loop iteration → consumes `agent.max_iterations`.
- Effective cap = `min(max_retries, max_iterations)`. Tune `Agent.max_iterations`
  (default 12) and the `sandbox_max_retries` config together.

### SSE events (additive)
| event | data |
|-------|------|
| `retry` | `{ name, attempt, max, reason }` — emitted before a retried step |
| `self_correct` | `{ status: "retrying" | "circuit_breaker", name, error }` |

Existing events (`message_start`, `token`, `tool_call`, `tool_result`,
`message_done`, `error`) are unchanged.

## 5. Security model

- **Filesystem**: hard jail via `safe_resolve`; agents cannot read/write outside
  `workspace/`.
- **Sandbox code**: ephemeral container, `--network none` by default (no egress),
  `--memory`/`--cpus` caps, writable `/work` only, no `--privileged`, no host PID.
  Artifacts are removed after each run.
- **Host shell** (`run_shell`) is intentionally unisolated and must be granted only
  to trusted agents.
- Network egress for the sandbox is off unless `sandbox_allow_network=true` (config).

## 6. Configuration

`backend/app/config.py`:
```python
workspace_dir: str = "./workspace"
max_iterations: int = 12          # per-agent overrideable on Agent
max_agent_depth: int = 5

# new sandbox settings
sandbox_enabled: bool = True
sandbox_docker_image_python: str = "python:3.11-slim"
sandbox_docker_image_bash: str = "bash:5"
sandbox_memory: str = "256m"
sandbox_cpus: float = 1.0
sandbox_default_timeout: float = 30.0
sandbox_allow_network: bool = False
sandbox_max_retries: int = 3
```

## 7. Docker runbook

### Prerequisites
- Docker Engine installed and running (`docker info` succeeds on the backend host).
- Sandbox images pulled once: `docker pull python:3.11-slim && docker pull bash:5`.

### Backend runs on the host (Linux/macOS/Windows+Docker Desktop)
- Works out of the box; the backend invokes the `docker` CLI.

### Backend runs inside a container
- Mount the Docker socket: `-v /var/run/docker.sock:/var/run/docker.sock` (Linux) or
  map Docker Desktop's socket on Windows. Without it, `run_code` returns
  `error: docker unavailable`.

### Troubleshooting
| Symptom | Cause / fix |
|---------|-------------|
| `error: docker unavailable` | Daemon not running or socket not mounted. |
| `error: ... no such image` | Pull the sandbox image(s). |
| `error: timed out` | Lower `code` cost or raise `sandbox_default_timeout`. |
| Agent loops forever retrying | Raises `circuit_breaker` after `sandbox_max_retries`; check `max_iterations`. |

## 8. Out of scope (v1)
- Live stdout streaming from the sandbox.
- Languages beyond python/bash.
- Pause/resume ("ask user when stuck") mode.
- Chat-UI rendering of `retry`/`self_correct` events (backend events shipped; UI is a
  follow-up).
