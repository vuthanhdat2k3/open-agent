# Module: Providers

## Purpose

Connect common LLM providers through a template-driven driver registry. A user
selects a provider template, enters an API key (optional for Ollama), and runs
a connection test. The backend discovers models and stores them disabled by
default until an administrator enables them.

## Built-in templates

| Template | Driver | Default endpoint |
|---|---|---|
| OpenAI | OpenAI-compatible | `https://api.openai.com/v1` |
| OpenRouter | OpenAI-compatible | `https://openrouter.ai/api/v1` |
| Ollama | OpenAI-compatible | `http://localhost:11434/v1` |
| Google Gemini | Native Gemini API | `https://generativelanguage.googleapis.com/v1beta` |
| Anthropic | Native Messages API | `https://api.anthropic.com` |
| OpenCode Zen | OpenAI-compatible | `https://opencode.ai/zen/v1` |
| DeepSeek | OpenAI-compatible | `https://api.deepseek.com/v1` |

The registry is static in `backend/app/core/providers/templates.py`. A
provider's `template_key` selects its driver; a legacy provider without a
template key continues to use the OpenAI-compatible driver.

## API

| Method | Path | Body / behavior |
|---|---|---|
| GET | `/api/providers/templates` | List templates and capability defaults |
| POST | `/api/providers/from-template` | `{template_key, api_key, base_url?, is_default?}`; test, discover and persist atomically |
| GET | `/api/providers` | List providers with discovery status and secret-safe key metadata |
| GET/PUT/DELETE | `/api/providers/{id}` | CRUD; empty API key on update preserves the existing key |
| POST | `/api/providers/{id}/test` | Re-test and synchronize models |

`providers:manage` is required for create/update/delete/test. Templates are
static metadata and require an authenticated request.

## Driver behavior

All drivers implement the same internal contract: `test_connection`,
`list_models`, `complete`, and `stream`, plus `supports_tools`,
`supports_reasoning`, and `supports_vision`. Anthropic and Gemini normalize
native message/tool-call/usage/stream formats into the internal event format
used by the agent loop. Model-level capability metadata overrides driver
defaults when the provider supplies it.

Network calls are made before the persistence transaction. Test timeout is 15
seconds and model discovery timeout is 20 seconds. Provider discovery failure
keeps the last successful model state. If model listing is unsupported, a
versioned fallback catalog may be stored as `source=fallback`, but fallback
models are never counted as live discovery and are disabled by default.

Ollama's default `localhost` endpoint is suitable for a locally running API.
When `OPENAGENT_RUNTIME=docker`, use `http://host.docker.internal:11434/v1`
or the Ollama service hostname in the advanced base URL override.

## Secret handling

Provider keys are encrypted at rest with AES-GCM. New writes use
`api_key_encrypted`; the plaintext migration column is blanked after the
backfill. Provider responses expose only `api_key_configured` and
`api_key_last4`, never the key itself. Configure
`OPENAGENT_CREDENTIAL_ENCRYPTION_KEY` in production; development falls back
to the legacy credential key and then the JWT secret for compatibility.

## Model lifecycle

Each model stores:

- `discovered`: sticky history — once discovered, never reset;
- `enabled`: administrator intent, default `false` for discovered models;
- `active`: stored runtime flag recomputed when discovery or model settings
  change;
- `last_seen_at`, `last_discovered_at`, `source`, catalog provenance, and
  capability overrides.

Only `active=true` models are returned by the default `/api/models` query and
therefore appear in Agent and Chat selectors. Administrators can use
`GET /api/models?with_inactive=true&q=...` to search and enable models. A
previously discovered model is kept through a seven-day grace period after it
stops appearing in a successful discovery response. A failed discovery does
not update `last_seen_at` or deactivate existing models.

## Layers

- `app/core/providers/templates.py` — static template registry.
- `app/core/providers/*_driver.py` — driver implementations.
- `app/core/providers/factory.py` — provider/model-aware driver factory.
- `app/services/model_discovery_service.py` — timeout, fallback and normalized model metadata.
- `app/services/provider_service.py` — provider CRUD, encryption, atomic persistence and re-sync.
- `app/repositories/provider_repo.py` / `model_repo.py` — tenant-scoped persistence.
- `app/api/v1/routes/providers.py` / `models.py` — thin API layer.
