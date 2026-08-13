# Langfuse Compose Integration Design

## Goal

Make the self-hosted Langfuse stack start with the main OpenAgent stack using
one command: `docker compose up -d --build`.

## Design

The common `docker-compose.yml` will own the Langfuse services: a dedicated
PostgreSQL database, Redis, ClickHouse, MinIO bucket initialization, Langfuse
web, and Langfuse worker. Langfuse will use its own database and Redis while
reusing the existing OpenAgent MinIO service. Langfuse services will have
healthchecks and dependency conditions so application containers start only
after their required dependencies are ready.

Existing Langfuse volume names are retained to preserve local data. The
OpenAgent exporter remains disabled by default; enabling it only requires the
existing `OPENAGENT_OBSERVABILITY_ENABLED`, `OPENAGENT_LANGFUSE_ENABLED`, and
key settings in `.env`.

## Verification

Validate the merged Compose configuration, start the stack, and confirm the
Langfuse web endpoint and worker healthchecks pass. No database version or
existing data will be changed by the Compose integration.
