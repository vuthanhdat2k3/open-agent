# Module: Langfuse observability

## Purpose

OpenAgent can export already-redacted LLM and tool observations to a self-hosted
Langfuse v4 instance. The exporter is off by default. `root_run_id` is returned
as `trace_id` by `GET /api/debug/tasks/{root_run_id}`; the same response includes
`langfuse_url` when `OPENAGENT_LANGFUSE_BASE_URL` is configured.

## Enable

1. Copy `.env.example` to `.env` and replace every `change-me` Langfuse value.
   Generate `LANGFUSE_ENCRYPTION_KEY` as 64 random hexadecimal characters.
2. Keep `LANGFUSE_INIT_PROJECT_PUBLIC_KEY`/`SECRET_KEY` equal to
   `OPENAGENT_LANGFUSE_PUBLIC_KEY`/`SECRET_KEY`.
3. Start the profile with the main stack:

   ```powershell
   docker compose -f docker-compose.yml -f docker-compose.langfuse.yml --profile langfuse up -d
   ```

4. Open `http://localhost:3002`; then set
   `OPENAGENT_OBSERVABILITY_ENABLED=true` and `OPENAGENT_LANGFUSE_ENABLED=true`.
   Containers use `http://langfuse-web:3000`; a host-run backend should use
   `http://localhost:3002` instead.

Langfuse Web is the only new public port. Its Postgres, ClickHouse, Redis and
worker remain inside the Compose network. Langfuse has its own database and
Redis instance; neither is shared with OpenAgent.

## Data controls

`ObservabilityContext._emit` centrally redacts, serializes and size-bounds every
record before the sink receives it. Callers cannot bypass that path. Configure:

- `OPENAGENT_OBSERVABILITY_CAPTURE_CONTENT`: global content permission.
- `OPENAGENT_OBSERVABILITY_SAMPLING_RATE`: deterministic per-trace content sampling.
- `OPENAGENT_OBSERVABILITY_MAX_CONTENT_BYTES`: upper bound after redaction.

Org, agent and request overrides can only disable capture; they cannot widen a
more restrictive parent policy. Metadata, model, status, latency and usage are
still exported when content capture is disabled.

## Operations

Validate configuration without starting services:

```powershell
docker compose -f docker-compose.yml -f docker-compose.langfuse.yml --profile langfuse config
```

Langfuse documents `/api/public/health` and `/api/public/ready` for Web, and
`/api/health` for Worker. The Compose health checks use these endpoints.

Back up Langfuse separately from OpenAgent:

```powershell
docker compose -f docker-compose.yml -f docker-compose.langfuse.yml exec -T langfuse-postgres pg_dump -U langfuse langfuse > langfuse-postgres.sql
docker compose -f docker-compose.yml -f docker-compose.langfuse.yml exec -T langfuse-clickhouse clickhouse-client --query "BACKUP DATABASE default TO Disk('backups', 'langfuse')"
```

Restore Postgres with `psql -U langfuse -d langfuse < langfuse-postgres.sql` and
ClickHouse with its matching `RESTORE DATABASE` command after copying the backup
to durable storage. Also back up the `minio-data` volume/bucket `langfuse-data`.
Langfuse recommends a self-hosted ClickHouse volume snapshot or native backup;
test restores before relying on any schedule.

Set retention using Langfuse project controls where available; otherwise apply a
documented ClickHouse TTL/S3 lifecycle policy after verifying it does not remove
data required for investigations. Monitor `llm_observability_export_failures_total`
and `llm_observability_dropped_events_total` for exporter health.
