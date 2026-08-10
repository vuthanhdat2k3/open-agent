# User-owned Google integrations

## Status

Implemented and verified.

## Goal

Allow each user to connect Gmail, Google Calendar, and Google Drive through the existing Google OAuth flow, while preventing users from viewing or disconnecting another user's connection in the same organization. Administrators retain organization-wide visibility and management.

## Design

- Keep the existing OAuth start/callback flow and encrypted credential storage.
- Make the Integrations navigation/page available to both roles.
- For a user, list only connections whose `created_by_user_id` equals the authenticated user. For an admin, preserve the current organization-wide list.
- Permit users to disconnect only their own connections. Enforce ownership in the backend, not only in the UI. Administrators may disconnect any connection in their organization.
- Preserve organization scoping and the OAuth state binding to the initiating user; no credentials are exposed to the browser.

## Implementation boundaries

- Reuse existing IntegrationsPanel and customer-intelligence repositories/services.
- Add the smallest shared filtering/authorization helper needed for connection list and disconnect operations.
- Do not change provider scopes, token encryption, or unrelated admin integration configuration.

## Verification

- Backend authorization and schedule tests pass; ownership filtering is enforced by the shared repository layer and route checks.
- Frontend typecheck/build passes and the user can reach `/integrations`.
- Existing backend suite remains green.
