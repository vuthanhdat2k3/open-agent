# Module: Providers

## Purpose
Manage **OpenAI-compatible** LLM endpoints. A single driver serves every
provider by varying `base_url`. Secrets are never stored — only the name of the
environment variable that holds the key.

## Data Model
See `database-schema.md §2.1 providers`. Key fields:
- `name` (unique), `base_url`, `api_key_env` (env var **name**, not value),
  `is_default`.

## API
| Method | Path | Body | Returns |
|--------|------|------|---------|
| GET | `/api/providers` | — | list |
| POST | `/api/providers` | `ProviderCreate` | created |
| GET/PUT/DELETE | `/api/providers/{id}` | `ProviderUpdate` | one |
| POST | `/api/providers/{id}/test` | — | reachability + model list |

## Behavior
- **Create**: validate `base_url` is `http(s)`. Persist only `api_key_env`
  (the actual key stays in the environment). Optionally set one provider
  `is_default=true` (enforced unique via service logic).
- **Test** (`POST /test`): read the key from `os.environ[api_key_env]`, call
  `GET {base_url}/models` (best-effort). Returns `ok` + discovered model ids so
  the UI can pre-fill the Models list. Non-fatal on failure (returns `ok:false`
  + error).
- **Delete**: blocked if models still reference it (service raises
  `ConflictError` → 409), or cascade-soft (v1: block with clear message).

## Layers
- `routes/providers.py` — thin; validates `ProviderCreate`/`ProviderUpdate`.
- `services/provider_service.py` — uniqueness of `is_default`, test connectivity,
  conflict checks.
- `repositories/provider_repo.py` — CRUD via SQLAlchemy async session.

## Frontend
- `app/providers/page.tsx`: table + create dialog.
- `components/providers/provider-form.tsx` (shadcn `Dialog` + React Hook Form +
  Zod). Zod mirrors `ProviderCreate`.
- `hooks/useProviders.ts` (TanStack Query): `useProviders`, `useCreateProvider`,
  `useTestProvider`.
- On create/test success → Sonner toast + invalidation.

## Security Note
We store `api_key_env`, never the value. At runtime the key is read and passed
to the OpenAI client; it is not logged. (Upgrade to a vault later if needed.)
