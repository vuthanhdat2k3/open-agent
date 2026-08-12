# Provider discovery after credential or endpoint updates

## Problem
`POST /api/providers/from-template` probes and persists models, but `POST /api/providers` and `PUT /api/providers/{id}` only persist provider fields. Updating NaraRouter's API key therefore leaves `discovery_status=pending` and no model catalog unless the operator separately clicks Test.

## Production design
Provider create/update remains a fast durable write. When credential or endpoint identity changes (`api_key`, `clear_api_key`, `base_url`, or `template_key`), the service increments a discovery generation, sets discovery state to `pending`, commits the encrypted credential, then enqueues a durable ARQ job after commit. The API does not wait for a remote `/models` call.

The worker reloads the provider by id, skips stale generations, marks the current generation as running, probes connection and model catalog with the existing `ModelDiscoveryService`, and persists the result through the existing `_persist_discovery` behavior. Discovery success updates catalog metadata without changing model `enabled`; failure preserves existing models and records an error. A job for a newer generation cannot be overwritten by an older job.

The existing explicit `POST /api/providers/{id}/test` remains the synchronous "Test now" path. Template creation keeps its current synchronous probe so "Test & Add Provider" remains atomic. Custom provider creation is unchanged in this focused fix; its update path and explicit Test both support rediscovery.

## Durability and failure handling
- Enqueue only after the provider transaction commits, so workers never observe uncommitted credentials.
- If enqueue fails after commit, the provider remains `pending`; a later reconciliation/retry can enqueue it without losing the credential.
- ARQ job arguments contain only provider id and generation, never API keys.
- Generation checks make retries and duplicate jobs idempotent and prevent stale results from overwriting a newer key's discovery.
- No model rows are deleted and existing `enabled` state is preserved.

## Data/API changes
Add a provider `discovery_generation` integer with a default of zero. `ProviderOut` exposes the generation and existing discovery status fields remain the UI contract. Update returns immediately with `discovery_status=pending` when rediscovery is queued.

## Validation
- Unit tests verify update enqueues only when discovery-relevant fields change, increments generation, and never queues plaintext credentials.
- Worker/service tests verify stale jobs are ignored, current jobs persist success, and failure preserves existing model state.
- Existing provider template tests and full backend suite remain green.
