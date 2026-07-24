# M10 - Agent Releases

## Branch

`agentos-v2/m10-agent-releases`

## Goal

Make agent configuration changes reviewable and reversible. Runtime executions
must identify the immutable release they used.

## Data Model

Add `AgentRelease`:

- `id`, `org_id`, `agent_id`
- monotonically increasing `version`
- `status`: `draft`, `published`, `archived`
- immutable configuration snapshot:
  `description`, `system_prompt`, `model_id`, `tools`,
  `allowed_risk_tiers`, `kind`, `max_iterations`, `temperature`
- `change_note`, `config_hash`
- `created_by_user_id`, `published_by_user_id`
- `created_at`, `published_at`
- unique `(agent_id, version)` and `(agent_id, config_hash)`

Add `Agent.active_release_id` and `Agent.latest_release_number`.
Chat sessions, workflow node runs, and tasks record the selected release where
the current execution path exposes a stable run record.

## API

- `GET /api/agents/{id}/releases`
- `POST /api/agents/{id}/releases` creates a draft snapshot.
- `GET /api/agents/{id}/releases/{version}`
- `POST /api/agents/{id}/releases/{version}/publish`
- `POST /api/agents/{id}/releases/{version}/rollback`

Publishing copies the immutable snapshot into the existing `Agent` runtime
columns in one transaction and updates `active_release_id`. Existing
`PUT /api/agents/{id}` remains backward compatible by creating and immediately
publishing a release.

## Authorization And Audit

- Read: `agents:read`
- Create draft: `agents:update`
- Publish/rollback: new `agents:publish`; owner/admin/developer receive it.
- Audit actions: `agent.release.create`, `agent.release.publish`,
  `agent.release.rollback`.

## Acceptance Criteria

- First agent creation creates release `1` and publishes it.
- Configuration snapshots are immutable after creation.
- Concurrent release creation cannot produce duplicate versions.
- Publishing is atomic and runtime reads the published snapshot.
- Rollback creates a new release; historical rows are never mutated.
- Cross-tenant release access returns 404.
- Existing agent CRUD/chat tests remain green.
- Migration upgrades both SQLite tests and PostgreSQL integration.
- Backend unit/integration tests, frontend typecheck/lint/build, Compose E2E,
  and CI all pass.

## Test Matrix

- Service tests: hashing, deduplication, publish, rollback, optimistic conflict.
- Route tests: RBAC and tenant isolation.
- Migration test: existing agents receive a release-1 backfill.
- Integration: create agent -> draft -> publish -> chat resolves active release.
- Browser E2E: inspect history, create draft, publish, rollback.

