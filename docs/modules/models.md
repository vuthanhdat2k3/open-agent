# Module: Models

## Purpose
Catalog models attached to providers, with cost/tier metadata used by the
metering engine and the model picker. One OpenAI-compatible driver means a model
is fully described by `(provider.base_url, model.name)`.

## Data Model
See `database-schema.md §2.2 models`. Key fields:
- `provider_id` (FK), `name` (API id, e.g. `gpt-4o-mini`), `display_name`,
  `tier` ∈ {`frontier`,`smart`,`balanced`,`fast`}, `context_window`,
  `input_cost_per_1k`, `output_cost_per_1k`, `active`.

## API
| Method | Path | Body | Returns |
|--------|------|------|---------|
| GET | `/api/models` | `?provider=&tier=&with_inactive=` | list |
| POST | `/api/models` | `ModelCreate` | created |
| GET/PUT/DELETE | `/api/models/{id}` | `ModelUpdate` | one |

## Behavior
- **List**: default returns only `active=true`. `with_inactive=true` includes
  inactive. Filter by `provider` and/or `tier`.
- **Cost**: `input_cost_per_1k` / `output_cost_per_1k` feed
  `core/llm.py` cost estimation: `cost = in/1000*in_rate + out/1000*out_rate`.
- **Tier** is a UI/router hint (not enforced routing in v1).
- **Uniqueness**: `(provider_id, name)` unique; creating a duplicate updates or
  rejects with 409.

## Layers
- `routes/models.py` — validate, pass query params.
- `services/model_service.py` — filter logic, uniqueness, cost helpers.
- `repositories/model_repo.py` — async queries.

## Frontend
- `app/models/page.tsx`: table with tier badge, cost columns, active toggle.
- `components/models/model-form.tsx`: provider `<Select>` (shadcn), tier
  `<Select>`, numeric cost inputs. Zod: `tier` enum, positive costs.
- `hooks/useModels.ts`: query + mutations; invalidation on change.
- Reused by Agent form (`model_id` select) and Workflow node config.

## Notes
- `context_window` is read by the compactor to decide when to summarize.
- Provider `/test` can auto-suggest models; the UI offers "import discovered
  models" which POSTs several `ModelCreate` in one batch (or sequentially).
