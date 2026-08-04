# Workspace Artifacts & Executions

This module gives users a control surface for files created by agents and for
code/shell executions started by agents or the sandbox API.

## Goals

- Show files written by agent tools such as `write_file`.
- Let users inspect, download, and delete generated workspace files.
- Record each sandbox or shell execution with status, timing, exit code, and
  output preview.
- Keep uploaded RAG documents separate from generated workspace artifacts.

## User Experience

Users get a **Workspace** page with two operational views.

### Artifacts

Users can:

- See every file generated inside the tenant workspace.
- Filter by path, agent, session, task, or source tool.
- Open text files inline for inspection.
- Download any artifact through the backend.
- Delete an artifact, which removes both the database record and the physical
  workspace file.
- See stale records when a file was removed outside the app.

Artifacts are created automatically when an agent calls `write_file`. The app
stores the relative path, size, content type, source tool, agent/session/task
context, and timestamps. The artifact table is not used for user uploads; those
remain in `uploaded_files` and MinIO.

### Executions

Users can:

- Review `run_code`, `run_shell`, and direct `/api/sandbox/run` executions.
- See whether an execution is `running`, `succeeded`, `failed`, or `timed_out`.
- Inspect language/command, exit code, duration, and output preview.
- Correlate an execution with agent, session, task, and root run IDs.
- Delete old execution records.

The current implementation records execution history. It does not yet provide a
live process list or a cancel/kill button because `run_code` uses one-shot
`docker run --rm` processes and the synchronous tool API returns after the
process exits. A later version can add a long-lived process supervisor with
cancel tokens.

## Data Model

### `workspace_artifacts`

- `org_id`
- `created_by_user_id`
- `agent_id`
- `session_id`
- `task_id`
- `root_run_id`
- `source_tool`
- `path`
- `content_type`
- `size`
- `sha256`
- `created_at`
- `updated_at`

`(org_id, path)` is unique so repeated writes update the same artifact record.

### `sandbox_executions`

- `org_id`
- `created_by_user_id`
- `agent_id`
- `session_id`
- `task_id`
- `root_run_id`
- `source`
- `language`
- `command`
- `status`
- `exit_code`
- `duration_ms`
- `stdout_preview`
- `error`
- `started_at`
- `finished_at`
- `created_at`

## API

All endpoints are tenant scoped.

- `GET /api/workspace/artifacts`
- `GET /api/workspace/artifacts/{id}`
- `GET /api/workspace/artifacts/{id}/content`
- `GET /api/workspace/artifacts/{id}/download`
- `DELETE /api/workspace/artifacts/{id}`
- `GET /api/workspace/executions`
- `GET /api/workspace/executions/{id}`
- `DELETE /api/workspace/executions/{id}`

Permissions:

- Artifact reads require `files:read`.
- Artifact deletes require `files:manage`.
- Execution reads require `usage:read`.
- Execution deletes require `usage:read` in the first implementation; a future
  admin-only cleanup permission can split this out.

### Run/Stop

Long-lived artifact execution: runs an artifact file in an ephemeral sandbox
container and streams its output. At most one concurrent run per organization.

- `POST /api/workspace/artifacts/{artifact_id}/run` — starts a run; body empty;
  `202` → `{execution_id, artifact_id, max_seconds}`.
  - `400` unsupported extension (only `.py` / `.sh`).
  - `404` unknown artifact.
  - `409` if another execution already runs for the org.
  - `401` / `403` unauthenticated / insufficient permission (`files:read`).
- `GET /api/workspace/executions/active` — `200` → `ActiveRunOut | null`
  (fields: `execution_id, artifact_id, path, language, started_at,
  remaining_seconds, max_seconds`).
- `GET /api/workspace/executions/{execution_id}/stream` — SSE
  (`text/event-stream`); events `stdout` (line), `stopped`, `timeout`, `exit`
  (code); heartbeat every 15s.
- `POST /api/workspace/executions/{execution_id}/stop` — `200` →
  `{"ok": true}`; `404` if the execution is not active.

Operational notes:

- The run executes the artifact file in an ephemeral sandbox container (tmpfs
  only, `--network none`, read-only root) — it does NOT write back to the host
  workspace.
- At most 1 concurrent run per organization.
- Default time limit `sandbox_max_run_seconds` = 600s with auto-stop → status
  `timed_out`.
- User Stop → status `stopped`.
- Clean exit → status `succeeded` / `failed`.
- The in-memory run registry is lost on backend restart; orphaned `oa-run-*`
  containers may remain.

## Tool Integration

- `write_file` upserts `workspace_artifacts` when a DB/org context exists.
- `run_code` creates a `sandbox_executions` row before Docker starts and updates
  it when the process exits, times out, or errors. Agent-triggered `run_code`
  receives a workspace snapshot inside Docker at `/work`, so code can read files
  previously created by `write_file`.
- `run_shell` records command execution history with `source="run_shell"`.
- `/api/sandbox/run` records direct user-triggered sandbox runs with
  `source="sandbox_api"`.

## Non Goals

- Replacing MinIO-backed user uploads.
- Copying arbitrary files created inside the Docker sandbox back to the host
  workspace automatically.
- Running unbounded background processes.
- Providing a kill button for already-detached processes.
