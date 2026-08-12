# Context Window Default 138000

## Scope
Use `138000` as the default context window across provider discovery, fallback catalog models, manually created model schemas, and ORM-created model rows.

## Compatibility and data safety
Existing discovered models whose `context_window` is exactly the previous fallback value `8192` are backfilled to `138000`. The migration only targets `source = 'discovered'`, so manually configured models and models with provider-supplied non-default context values are preserved. No model enablement, active state, pricing, or provider credentials are changed.

## Implementation
Define one shared `DEFAULT_CONTEXT_WINDOW` constant and use it wherever the application currently hard-codes the generic context default. Add an Alembic migration for the conditional backfill. Discovery continues to preserve provider-supplied context values when present and only uses the shared default when metadata is absent.

## Validation
Add regression coverage for the shared default and conditional backfill. Run provider tests, backend static checks, and a runtime query confirming the NaraRouter catalog uses `138000` without changing model count or enabled state.
