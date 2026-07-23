# M12 - Tenant Quotas And Admission Control

## Branch

`agentos-v2/m12-tenant-quotas`

## Goal

Protect a shared deployment from accidental overload and uncontrolled spend
without weakening tenant isolation.

## Limits

Add one `OrganizationQuota` per organization:

- `requests_per_minute`
- `agent_runs_per_minute`
- `max_concurrent_runs`
- `monthly_cost_usd`
- optional `max_agents`, `max_workflows`, `max_storage_bytes`
- `enforcement_mode`: `enforce`, `observe`
- `updated_at`, `updated_by_user_id`

Defaults are configurable and safe for self-hosted development.

## Enforcement

- Redis Lua scripts implement atomic sliding-window admission and concurrent
  run leases across API replicas.
- Run leases have TTL and are released in `finally`; stale workers cannot hold
  capacity forever.
- Monthly spend uses durable `UsageEvent` totals as source of truth and a
  short-lived Redis cache for admission speed.
- Mutating/run endpoints fail closed if Redis is unavailable in `enforce`
  mode. Read and health endpoints are not blocked.
- Responses use HTTP `429` with `Retry-After` and standard
  `RateLimit-Limit`, `RateLimit-Remaining`, and `RateLimit-Reset` headers.

## API And Permissions

- `GET /api/orgs/{id}/quota`: owner/admin.
- `PUT /api/orgs/{id}/quota`: owner only by default.
- `GET /api/orgs/{id}/quota/usage`: owner/admin/developer.
- New permissions: `quota:read`, `quota:manage`.

## Observability

- Prometheus counters by limit type and decision, never by raw org id.
- Structured admission logs include request id and a hashed tenant key.
- Audit every quota mutation.
- Dashboard panels show rejection rate, active leases, and Redis failures.

## Acceptance Criteria

- Limits are isolated per tenant and correct across two API processes.
- Sliding-window boundary tests do not allow bursts above configured capacity.
- Concurrent leases release on success, exception, cancellation, and TTL.
- Monthly budget rejects the next run after recorded usage reaches the limit.
- Observe mode emits metrics/headers but does not reject.
- 429 responses are consistent through direct API and frontend proxy.
- Redis integration test and Docker Compose E2E pass.
- Full backend, frontend, RAG, migration, and browser regressions pass.

