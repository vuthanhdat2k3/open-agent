# Calendar event response reconciliation

## Problem

Google Calendar successfully creates an event and returns its canonical event
identifier as `provider_event_id`. The delivery executor currently only checks
`id` and `event_id`, so a successful provider call can remain `pending` and be
retried.

## Design

- The calendar provider contract exposes `provider_event_id` as the canonical
  identifier.
- The executor accepts `provider_event_id` first, with `id` and `event_id` as
  compatibility fallbacks for older providers.
- A response without any identifier is treated as a failed/ambiguous delivery;
  it must not be marked delivered.
- Existing pending attempts are never blindly replayed. Reconciliation must
  verify the provider result before another create call.

## Verification

- Unit test: canonical `provider_event_id` marks a delivery delivered.
- Unit test: legacy `id`/`event_id` responses remain supported.
- Unit test: missing identifier does not mark delivery delivered.
- Live verification: the existing approved case is reconciled without creating
  a second Google Calendar event.
