# Provider Templates & Native Driver Support — Design Spec

Date: 2026-08-10
Status: Approved by user, pending implementation plan

## 1. Problem

OpenAgent currently supports only OpenAI-compatible endpoints
(`backend/app/core/llm.py` wraps `AsyncOpenAI`). Adding a provider means
manually filling in `key/name/base_url/api_key/env_var` with no guidance, and
there is no native support for providers with a different wire protocol
(Anthropic Messages API, Google Gemini). Models are also entered by hand with
no discovery from the provider.

## 2. Goal

Add one-click provider templates for seven common providers. Selecting a
template pre-configures driver, auth strategy, and base URL; the user only
enters an API key and clicks test. On successful test, the backend discovers
available models from the provider and stores them as disabled-by-default.
Add a model management view with search and enable/disable, and restrict
Agent/Chat model pickers to enabled+active models only.

Templates: **OpenAI, OpenRouter, Ollama, Google Gemini, Anthropic, OpenCode
Zen, DeepSeek**.

## 3. Non-goals

- No background job queue in this iteration (discovery runs synchronously
  with a hard timeout; the status fields are designed to support a future
  `creating → testing → discovering → ready` job without a schema change).
- No automatic assignment of newly discovered models to any agent.
- No change to the manual "New Model" form/flow for hand-entered models
  beyond displaying the new lifecycle/provenance fields.
- No new provider template beyond the seven listed (users can still add a
  fully custom/manual provider as today).
- No multi-key-per-provider or per-model key support.

## 4. Architecture

Three layers, so the OpenAI-only `LLMClient` used directly by
`agent_loop.py`, `workflow_service.py`, `compactor.py`, and
`core/memory/tiers.py` is replaced by a common contract:

```
TemplateRegistry (static, in-code)
        v
DriverRegistry / LLMDriver (protocol + 2 implementations)
        v
ProviderService + ModelDiscoveryService (transactional persistence)
```

### 4.1 TemplateRegistry

A static, in-code registry (`backend/app/core/providers/templates.py`) — not
a DB table — listing the 7 templates. Each entry:

```python
class ProviderTemplate:
    key: str                     # "openai", "openrouter", "ollama",
                                  # "gemini", "anthropic", "opencode", "deepseek"
    display_name: str
    driver: Literal["openai_compatible", "anthropic", "gemini"]
    default_base_url: str
    api_key_required: bool       # False only for "ollama"
    supports_tools: bool
    supports_reasoning: bool
    supports_vision: bool
    fallback_models: list[FallbackModelSpec]   # used only if discovery fails/unsupported
    catalog_version: str          # bumped when fallback_models changes
```

`GET /api/providers/templates` returns this list (no secrets involved, no
auth required beyond normal login).

### 4.2 LLMDriver contract

```python
class ModelInfo(TypedDict):
    name: str
    display_name: str
    context_window: int | None
    input_cost_per_1k: float | None
    output_cost_per_1k: float | None
    supports_tools: bool | None       # None => inherit driver default
    supports_reasoning: bool | None
    supports_vision: bool | None

class LLMDriver(Protocol):
    supports_tools: bool
    supports_reasoning: bool
    supports_vision: bool

    async def test_connection(self) -> TestResult: ...
    async def list_models(self) -> list[ModelInfo]: ...
    async def complete(self, messages, tools=None, temperature=0.7, tool_choice=None) -> ...: ...
    def stream(self, messages, tools=None, temperature=0.7, tool_choice=None) -> AsyncIterator[dict]: ...
```

`complete`/`stream` return the same internal event contract already used by
`LLMClient` today (`{"type": "content"|"reasoning"|"tool_calls"|"usage", ...}`),
so callers in `agent_loop.py`/`compactor.py`/etc. do not change their event
handling — only how the driver is constructed changes.

Two concrete drivers:

- **`OpenAICompatibleDriver`** — thin rename/wrap of the current `LLMClient`
  logic. Backs `openai`, `openrouter`, `ollama`, `opencode`, `deepseek`, and
  any legacy/custom provider (`template_key IS NULL`). Auth:
  `Authorization: Bearer <key>`. Ollama: key is optional; if empty, the
  header is omitted.
- **`AnthropicDriver`** — native Messages API (`x-api-key` +
  `anthropic-version` headers). Normalizes Anthropic's content blocks, tool
  use blocks, and usage into the shared internal event contract.
- **`GeminiDriver`** — native Google Gen AI SDK/API. Auth per SDK
  convention. If the SDK/API requires a query-string key, the driver must
  redact it before any logging/audit write (see §7).

A `build_driver(provider: Provider, model: Model) -> LLMDriver` factory
replaces every direct `LLMClient(provider.base_url, resolve_api_key(provider),
model.name)` call site. Call sites to change:
`backend/app/core/agent_loop.py`, `backend/app/services/workflow_service.py`,
`backend/app/core/compactor.py`, `backend/app/core/memory/tiers.py`.

Effective capability for a model = model's own
`supports_tools/reasoning/vision` if not `None`, else the driver's default.

### 4.3 ProviderService + ModelDiscoveryService

`ModelDiscoveryService` is new; `ProviderService` gains a `create_from_template`
method. Persistence is transactional; network calls are not:

```
1. Validate template_key exists; normalize base_url (trim trailing slash;
   for ollama, if OPENAGENT_RUNTIME=docker and host is localhost/127.0.0.1,
   attach a warning — do not rewrite the URL automatically).
2. Build driver from template + api_key (not yet persisted).
3. OUTSIDE any DB transaction, with a hard timeout:
   a. driver.test_connection()   — 15s timeout
   b. driver.list_models()       — 20s timeout
4. If test_connection fails: return 400 with the error; nothing persisted.
5. If list_models fails/times out: proceed with discovery_status="failed",
   discovery_error=<msg>, models_discovered=0, and fall back to
   template.fallback_models tagged source="fallback" (still created as
   disabled models) — only for templates where fallback exists (all 7 do).
6. Open one DB transaction:
   a. Upsert Provider on (org_id, template_key, normalized_base_url):
      if found, update api_key_encrypted + refresh status fields;
      if not found, insert new row.
   b. For each discovered/fallback model, upsert Model on
      (provider_id, name): update discovery metadata, but never touch
      `enabled` if the row already exists.
   c. Update provider.discovery_status/discovery_error/models_discovered/
      last_discovery_attempt_at, and last_successful_discovery_at only if
      step 3b succeeded.
   d. Commit.
7. Return ProviderOut (no api_key).
```

Idempotency is enforced by a DB unique constraint on
`(org_id, template_key, normalized_base_url)` (nullable-safe: legacy rows with
`template_key IS NULL` are excluded from this constraint — see §5), not only
an application-level check-then-insert, so concurrent calls cannot create
duplicates.

If step 6 (persistence) raises, the transaction rolls back; no provider is
left half-created. If discovery (step 3) fails outright before any
persistence, nothing exists yet — no rollback needed, consistent with "no
network calls inside a DB transaction."

Re-syncing an existing provider (`POST /api/providers/{id}/test`) follows the
same discovery step but only ever updates that one provider row plus its
models — same "keep old data on failure" rule.

## 5. Data model changes

### `providers` table (additive, all nullable/defaulted — backward compatible)

| Column | Type | Notes |
|---|---|---|
| `template_key` | `String(32)`, nullable | `NULL` for legacy/custom providers |
| `api_key_encrypted` | `Text`, nullable | AES-GCM ciphertext; replaces plaintext storage |
| `api_key_last4` | `String(8)`, nullable | Derived at write time, cached for display |
| `status` | `String(16)`, default `"ready"` | `creating`\|`ready`\|`error` |
| `discovery_status` | `String(16)`, default `"pending"` | `pending`\|`complete`\|`partial`\|`failed` |
| `discovery_error` | `Text`, nullable | Last discovery error message |
| `models_discovered` | `Integer`, default `0` | Count of models with `source="discovered"` from the last successful discovery run only; fallback models are never counted here, so a `discovery_status="failed"` row always shows `models_discovered=0` regardless of how many fallback models exist |
| `last_discovery_attempt_at` | `DateTime`, nullable | Every attempt, success or failure |
| `last_successful_discovery_at` | `DateTime`, nullable | Only successful discovery runs |

`api_key` (plaintext column) stays for one migration cycle for read
compatibility during rollout, but is no longer written; a migration backfills
`api_key_encrypted` from it and blanks it out (see §8). `ProviderOut` never
serializes either column directly — see §7.

New partial unique index (Postgres/SQLite both support partial indexes):
`uq_providers_org_template_baseurl ON providers (org_id, template_key,
normalized_base_url) WHERE template_key IS NOT NULL`. `normalized_base_url`
is a stored column (lowercased, trailing slash stripped) set on write, not a
computed expression, to keep it portable across SQLite/Postgres.

### `models` table (additive)

| Column | Type | Notes |
|---|---|---|
| `discovered` | `Boolean`, default `False` | Sticky true once ever discovered; never reset to `False` |
| `enabled` | `Boolean`, default `False` | User intent; discovery never overwrites an existing value |
| `last_seen_at` | `DateTime`, nullable | Updated only on successful discovery that includes this model |
| `source` | `String(16)`, default `"manual"` | `discovered`\|`fallback`\|`manual` |
| `catalog_source` | `String(64)`, nullable | e.g. `"opencode-fallback-v1"`; set only for `source="fallback"` |
| `catalog_version` | `String(16)`, nullable | Template's `catalog_version` at insert time |
| `last_discovered_at` | `DateTime`, nullable | Timestamp of the discovery run that produced/refreshed this row |
| `supports_tools` | `Boolean`, nullable | `NULL` => inherit driver default |
| `supports_reasoning` | `Boolean`, nullable | |
| `supports_vision` | `Boolean`, nullable | |

`active` (existing column) stays a real stored `Boolean` column — existing
call sites (`app/repositories/model_repo.py:list_active`,
`app/core/agent_loop.py` model_id validation) filter with
`Model.active.is_(True)` in raw SQL, which cannot target a Python-only
computed property. Instead, `active` becomes a **derived value that is
recomputed and written** at the points where a model row is touched, rather
than a field the caller sets directly:

`active = enabled AND (source != "discovered" OR last_seen_at IS NULL OR now() - last_seen_at <= GRACE_PERIOD)`

`GRACE_PERIOD = 7 days` (constant in `model_service.py`, not user-configurable
in this iteration). Manual models (`source="manual"`) are never subject to
the grace period — `active = enabled` for them.

Recomputation happens in two places, both of which write the column:
1. Every discovery run (`ModelDiscoveryService`), for every model belonging
   to that provider — including ones not present in the current discovery
   result (so a model that just fell outside the grace period gets
   `active=False` written even though this discovery run didn't mention it).
2. `ModelService.update()` (the `PUT /api/models/{id}` path), whenever
   `enabled` changes — recomputes `active` immediately so a manual toggle
   takes effect without waiting for the next discovery run.

There is no periodic sweep job in v1: a provider that is never re-tested
keeps stale `active=True` models past the grace period until the next
discovery run or manual edit recomputes them. This is an accepted limitation
for this iteration, not a silent correctness bug — call out in the PR
description if a scheduled re-sync is not implemented alongside this.

Existing rows get `discovered=False, enabled=<existing value of active>,
source="manual"` via backfill migration, preserving current behavior for
pre-existing data.

## 6. API changes

| Method | Path | Auth | Notes |
|---|---|---|---|
| GET | `/api/providers/templates` | any authenticated user | Static list, no secrets |
| POST | `/api/providers/from-template` | `providers:manage` | Body: `{template_key, api_key, base_url?, is_default?}`. `base_url` optional override (required use case: Ollama in Docker). Returns `ProviderOut` with discovery status |
| POST | `/api/providers/{id}/test` | `providers:manage` | Re-runs test + discovery for an existing provider (existing endpoint, behavior extended) |
| GET/POST/PUT/DELETE | `/api/providers` | existing permissions | Unchanged request contract; response contract changes (see §7) for all providers, template-based or not |
| GET | `/api/models` | `models:read` | Adds optional `?q=` search and `?with_inactive=` (already documented, now actually implemented consistently); response includes new lifecycle fields |
| PUT | `/api/models/{id}` | `models:manage` | Body may now include `enabled` (preferred) — `active` remains accepted for backward compat but is documented as derived/overridable-by-admin only for manual models |

No new permission strings; reuses `providers:read`, `providers:manage`,
`models:read`, `models:manage` already defined in
`backend/app/core/authz/policy.py`.

`ProviderCreate`/`ProviderUpdate` schemas (existing manual flow) are
unchanged in shape — `api_key` is still accepted as plaintext input — only
the storage (`resolve_api_key`/service layer now encrypts on write) and the
response schema change.

## 7. Secret handling

- Reuse the existing AES-GCM helper in
  `backend/app/customer_intelligence/security.py` (`encrypt_bytes`/
  `decrypt_bytes`), extracted into a shared
  `backend/app/core/security/secrets.py` module so both Customer Intelligence
  and Providers use the same primitive without duplicating crypto code.
- New setting `ci_credential_encryption_key` is renamed conceptually to a
  shared `credential_encryption_key` setting; for backward compatibility the
  existing env var name is kept and a new `OPENAGENT_CREDENTIAL_ENCRYPTION_KEY`
  alias is documented, defaulting to the same dev fallback (derived from
  `jwt_secret_key`) — production deployments are expected to set it
  explicitly (documented in README, not enforced by a hard fail in this
  iteration to avoid breaking existing deployments silently).
- `ProviderOut` schema drops `api_key` entirely and adds:
  `api_key_configured: bool`, `api_key_last4: str | None`.
- `ProviderUpdate`: if `api_key` is omitted or empty string, the existing
  encrypted key is preserved unchanged. Explicit key removal (rare) requires
  a distinct `clear_api_key: bool = True` field — no removal via empty
  string.
- No API key value is ever written to `structlog` logs, OpenTelemetry spans,
  or the audit log. Driver implementations must build request URLs without
  interpolating the key into a loggable string; if a driver's SDK requires a
  query-string key (Gemini, if applicable), the driver must pass a redacted
  placeholder to any logging/tracing call.

## 8. Migration plan

New Alembic revision (`backend/alembic/versions/00XX_provider_templates.py`),
following the existing `batch_alter_table` pattern (see `0022`, `0023`):

1. Add new nullable/defaulted columns to `providers` and `models` as in §5.
2. Add `normalized_base_url` column to `providers`, backfill from existing
   `base_url` (lowercase, strip trailing slash) for all existing rows.
3. Add the partial unique index on `providers`.
4. Data migration: for every provider with non-empty `api_key`, compute
   `api_key_encrypted` + `api_key_last4`, then set `api_key = ""`.
5. Data migration: for every existing model, set
   `discovered=False, source="manual", enabled=<current active value>`.
   Leave `active` column in place (still read by any code not yet migrated)
   but stop writing to it directly from discovery paths after this release.

Rollback (`downgrade`) drops the added columns/index; it does not attempt to
restore plaintext `api_key` (already zeroed) — this is called out explicitly
as a one-way step in the migration's docstring, matching how other
irreversible backfills in this repo are documented.

## 9. Frontend changes

- `frontend/app/providers/page.tsx`: "New Provider" dialog gains a template
  picker step (7 template cards) before the existing manual form; picking a
  template shows only an API key input (+ optional base URL override,
  collapsed under "Advanced", primarily for Ollama) and a "Test & Add"
  button. The existing manual/custom provider form remains available as a
  separate "Custom provider" option for parity with today's behavior.
- Provider list card: remove `p.api_key.slice(-4)` (the field no longer
  exists); replace with `p.api_key_configured` badge and `p.api_key_last4`.
  Add discovery status badge (`ready`/`partial`/`failed`) and
  `models_discovered` count.
- Ollama template: static warning text ("running in Docker? use
  `http://host.docker.internal:11434/v1`") shown only when the backend's
  `/api/health` (or an existing settings-exposing endpoint) reports Docker
  runtime; otherwise hidden. Exact plumbing of the runtime flag to the
  frontend is an implementation detail resolved in the implementation plan,
  not a new public API surface beyond exposing `runtime` on the existing
  health/config response.
- `frontend/app/models/page.tsx`: add a search input (client-side filter over
  `useModels({with_inactive: true})` result) and an enable/disable toggle per
  model card (calls `PUT /api/models/{id}` with `{enabled}`). Show
  `source`/`discovered`/`last_seen_at` metadata in the card.
- Agent form model `<Select>` and Chat model switcher: both already read from
  `useModels()`; change the query to request only `active=true` (default,
  unchanged) — no behavior change needed there beyond the backend correctly
  filtering, since they already rely on the default (non-`with_inactive`)
  list endpoint.
- `frontend/types/index.ts` / `frontend/lib/schemas.ts`: update `Provider`
  and `Model` types to match the new fields; remove `api_key` from the
  `Provider` interface.

## 10. Testing plan

Backend (pytest):

- `TemplateRegistry` returns exactly 7 templates; no secret fields.
- Each driver: `test_connection`/`list_models`/`complete`/`stream` against a
  mocked HTTP layer (httpx mock / respx) — auth header/placement correct per
  driver; no key appears in any raised exception message or log capture.
- `create_from_template`: success path persists provider + models atomically;
  failure of `test_connection` persists nothing; failure of `list_models`
  persists provider with fallback models and `discovery_status="failed"`.
- Idempotency: two sequential calls with the same
  `(org_id, template_key, base_url)` update the same row, never duplicate;
  concurrent calls (simulated) don't violate the unique constraint silently
  (second call updates, doesn't 500).
- `api_key` round-trip: stored encrypted, never present in any response body;
  empty-string update preserves the existing key.
- Model lifecycle: new discovered model is `enabled=False`; re-discovery does
  not flip a user-enabled model back to `False`; `discovered` never resets to
  `False`; grace period correctly toggles computed `active`.
- Discovery failure on re-sync (`POST /{id}/test`) leaves existing models and
  `last_successful_discovery_at` untouched, only updates
  `discovery_status`/`discovery_error`/`last_discovery_attempt_at`.
- Capability resolution: model-level `supports_tools=False` overrides a
  driver whose default is `True`; `None` falls back to driver default.
- `GET /api/models` default excludes inactive; `with_inactive=true` +
  `q=` search both work; Agent/Chat pickers only ever see active models
  (existing `agent_loop.py` model_id validation already filters
  `Model.active.is_(True)` for the `user` role — extend/verify it also holds
  for the default agent-loop path with the new computed `active`).

Frontend (typecheck/lint/build + targeted component checks):

- Template picker renders 7 cards; selecting one hides base URL / shows only
  API key + advanced toggle.
- Provider card never renders a raw API key string.
- Models page search/filter and enable toggle call the right hook/endpoint.

## 11. Rollout / compatibility summary

- Legacy providers (`template_key IS NULL`) keep working unchanged through
  `OpenAICompatibleDriver`.
- Existing manual "New Model" flow is untouched functionally; only new
  read-only metadata fields are surfaced in the UI.
- No new required environment variables; encryption key falls back to the
  existing JWT secret in dev, with the production expectation documented in
  README (not enforced in this iteration).
