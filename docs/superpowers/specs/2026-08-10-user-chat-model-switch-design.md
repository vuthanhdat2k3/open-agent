# User Chat Model Switching

Date: 2026-08-10
Status: Implemented and live-verified

## Goal

Allow a `user` to choose among models already configured by an admin for the
active organization, while keeping the user restricted to the organization's
orchestrator agent.

## Behavior

- The user Chat model picker is enabled for active, organization-scoped models
  returned by the existing model read endpoint.
- A selected `model_id` applies to that chat request/session only. It does not
  change the orchestrator's configured default or affect other users.
- If no model is selected, the orchestrator's current default model remains the
  fallback.
- User permissions remain read-only for model metadata: no model/provider
  create, update, delete, or provider credential access.
- Agent selection remains locked to the orchestrator for users. Admin behavior
  is unchanged.

## Backend contract

- The chat request's existing `model_id` field is used; no new public API shape
  is required.
- Before starting a user chat, validate that the selected model belongs to the
  active organization and is active. Reject cross-organization, inactive, or
  missing models with a client-visible validation error.
- Continue resolving the agent from the user's permitted orchestrator scope;
  a model choice must never grant access to a worker agent.

## Frontend contract

- Reuse the existing Chat header model picker and model query.
- Render the picker for both roles when active models exist.
- Keep the agent selector static for users and fully interactive for admins.
- Preserve loading, empty, and unavailable-model states without exposing admin
  configuration controls.

## Verification

- Backend regression tests cover valid same-organization model selection,
  inactive/cross-organization rejection, and unchanged orchestrator-only agent
  visibility.
- Frontend typecheck/build pass.
- Docker live test covers a user selecting an admin-configured model in Chat,
  receiving a response, and confirms admin model configuration remains intact.

## Result

- Backend regression coverage passes as part of the full **245-test** suite.
- Docker live verification selected `Qwen 3.6 fast` as `user@openagent.com` and
  received `USER_MODEL_SWITCH_OK`; the persisted usage event matched the
  selected model and user owner.
