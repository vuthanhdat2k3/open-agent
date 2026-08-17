# Greenfield Enterprise Identity and Authorization Production Design

**Date:** 2026-08-17

**Status:** Approved architecture; written specification awaiting review

**Related design:** `2026-08-15-enterprise-rbac-zitadel-design.md`

## 1. Decision and relationship to the earlier design

OpenAgent has not been deployed to production and has no production identities or organizations to preserve. The first production release will therefore start directly with ZITADEL as its only human identity authority. It will not implement a per-organization legacy-to-ZITADEL pilot, dual authentication, an `authority_mode` migration field, or a legacy rollback path.

This specification retains the target architecture, role model, provisioning, synchronization, audit, and operational requirements from the 2026-08-15 design. It supersedes that document only where it assumes migration of existing production users, dual-read verification, staged organization cutover, or temporary legacy authentication.

The production release is blocked until the complete identity and authorization acceptance gate in this document passes against a real pinned ZITADEL container. Unit tests with mocked identity responses are necessary but are not sufficient.

## 2. Goals

1. Make ZITADEL the only source of truth for human credentials, identity status, MFA, SSO, and project role assignments.
2. Remove public registration, application-owned passwords, legacy OAuth JIT provisioning, local JWT issuance, refresh tokens, and the global `OPENAGENT_API_KEY` fallback before the first production release.
3. Centralize authorization into an explicit permission and resource-scope decision.
4. Enforce the intersection of principal permissions, organization policy, agent capability, tool risk, and object ownership at every runtime entry point.
5. Introduce fixed organization roles `org_admin`, `operator`, and `user`, plus a separate platform control-plane authority.
6. Replace user-inheriting API keys with service principals and fixed, expiring scopes.
7. Enforce risk-based approval separation of duties using immutable server-side tool risk classifications.
8. Make personal files owner-scoped and organization knowledge explicitly organization-scoped.
9. Fail closed when provisioning, identity projection, membership state, scope resolution, or signature validation is uncertain.
10. Prove the production path through real-container E2E tests before any external user is onboarded.

## 3. Non-goals

- Migrating real production users, passwords, refresh tokens, organizations, or API keys; none exist.
- Preserving development and test identities during the cutover; those databases are disposable and must be reseeded through the supported provisioning flow.
- Supporting legacy and ZITADEL authentication simultaneously in production.
- Adding `Organization.authority_mode`; there is exactly one production authority.
- Public, domain-only, or callback-driven account creation.
- Custom organization roles in the first production release.
- Allowing the ZITADEL role claim alone to authorize access to OpenAgent data.
- Giving platform administrators implicit access to customer content.
- Treating UI visibility as an authorization boundary.
- Using product API keys for platform identity administration or first-party service-to-service authentication.

## 4. Options considered

### 4.1 Selected: greenfield direct cutover

Build and verify the complete target architecture before the first production release. Development may land the work in independently testable branches, but the production release gate remains closed until legacy auth is removed and real ZITADEL E2E passes.

This avoids migration-only states, prevents accidental authority fallback, and does not spend engineering time hardening an identity system that will never serve production users.

### 4.2 Rejected: per-organization staged cutover

This is the safest choice for an already deployed system, but it introduces an authority-mode state machine, token revocation by organization, dual-path runbooks, and migration reconciliation that have no production data to protect.

### 4.3 Rejected: retain hybrid authentication

Keeping password/JWT and ZITADEL indefinitely creates two credential authorities, makes deprovisioning ambiguous, complicates audit attribution, and increases the attack surface. No fallback from ZITADEL to local credentials is allowed.

## 5. Trust boundaries and architecture

```text
Browser
  |  OIDC Authorization Code + PKCE
  v
ZITADEL <-------- platform provisioning worker
  |                            |
  | verified code/claims       | narrowly scoped IAM service identity
  v                            v
OpenAgent API ----------> PostgreSQL projection
  |                         | users / memberships / sessions
  | AuthorizationDecision   | service principals / invitations
  v                         | provisioning / identity events
Domain services             v
  |                    durable outbox + worker
  v
Agents / tools / files / workflows / approvals
```

Trust ownership:

- **ZITADEL:** human credentials, MFA, external IdP federation, identity status, customer organizations, project grants, and project role assignments.
- **OpenAgent:** product organizations, local identity projection, application sessions, permissions, scopes, ownership, approvals, product API keys, and business audit.
- **PostgreSQL:** authoritative enforcement projection for a request after ZITADEL authentication. Missing or stale security-critical projection denies access.
- **Backend worker/outbox:** durable provisioning, event processing, retries, and reconciliation.
- **Frontend:** initiates OIDC and renders capabilities returned by the backend; it never decides authorization.

## 6. ZITADEL deployment

### 6.1 Version and topology

- Pin the ZITADEL container to an explicit released version and immutable image digest; never use `latest`.
- Local development and CI use Docker Compose with ZITADEL, PostgreSQL, a local SMTP sink, OpenAgent API, worker, and frontend.
- Production uses a dedicated ZITADEL PostgreSQL database and database principal. Sharing a PostgreSQL cluster is permitted; sharing the OpenAgent database/schema is not.
- Production separates `zitadel init`, `zitadel setup`, and stateless `zitadel start` workloads.
- The public ZITADEL domain is served through TLS and a reverse proxy that supports HTTP/2.
- ZITADEL configuration is stored as reviewed configuration files; secrets are injected by the deployment secret manager.

The official production guidance recommends high availability, separate initialization/setup for scalable runtime workloads, TLS, HTTP/2-capable proxying, PostgreSQL, metrics, and database backup. Those controls are deployment requirements, not optional application features.

### 6.2 Bootstrap as code

An idempotent bootstrap job creates or verifies:

- the platform organization;
- the OpenAgent project;
- web OIDC application and exact redirect/logout URIs;
- API/IAM service application with the minimum management permissions;
- fixed project roles `org_admin`, `operator`, and `user`;
- Actions v2 targets/executions used by lifecycle synchronization;
- default policy with public self-registration disabled;
- SMTP and invitation templates;
- production token/session policy.

The bootstrap job reads identifiers after creation and persists them in secret/configuration storage. A mismatch between configured and observed immutable identifiers stops startup; it does not create duplicates.

### 6.3 Readiness and operations

Readiness requires ZITADEL discovery, JWKS, database, and configured application metadata to be available. Monitoring covers authentication error rate, Actions delivery, projection lag, reconciliation drift, PostgreSQL health, certificate expiry, SMTP delivery, and backup freshness.

Production backup must include a tested PostgreSQL restore procedure. A successful backup without a restore test does not satisfy the release gate.

## 7. Human authentication and application sessions

### 7.1 Login flow

```text
GET /api/auth/login?organization=<slug>
-> resolve active local organization and its zitadel_org_id
-> create state, nonce, PKCE verifier/challenge, and short-lived login transaction
-> redirect to ZITADEL
-> ZITADEL authenticates and returns authorization code
-> callback validates state and exchanges code with PKCE verifier
-> validate issuer, audience, signature, nonce, expiry, subject, and organization context
-> require active local User, Membership, and Organization projection
-> create opaque organization-bound application session
-> set secure session and CSRF cookies
```

ZITADEL recommends Authorization Code with PKCE for browser and web clients. OpenAgent uses a backend-for-frontend session so ZITADEL access, ID, and refresh tokens are never stored in browser local storage.

### 7.2 No JIT provisioning

The authentication callback may update non-authoritative display attributes, but it cannot create an organization, user, membership, invitation, role, or service principal. An authenticated subject without an active projection receives `403 ACCOUNT_NOT_PROVISIONED` with no account-enumeration detail.

### 7.3 Session model

Add `application_sessions`:

```text
id
session_token_hash           unique; raw token exists only in HttpOnly cookie
user_id
organization_id
membership_id
zitadel_session_id           nullable when unavailable
auth_time
last_seen_at
idle_expires_at
absolute_expires_at
revoked_at
revocation_reason
created_ip_hash
created_user_agent_hash
created_at
```

Session cookies are `HttpOnly`, `Secure`, and `SameSite=Lax` by default. Every state-changing cookie-authenticated request requires a session-bound CSRF token. Organization switching revalidates membership and rotates both session and CSRF tokens.

Role change, suspension, membership removal, user deactivation, organization suspension, and confirmed ZITADEL session revocation invalidate affected application sessions.

### 7.4 Removed legacy surfaces

Remove before production release:

```text
POST /api/auth/register
POST /api/auth/login               application password variant
POST /api/auth/refresh             application refresh-token variant
GET  /api/auth/oauth/{provider}    legacy Google/GitHub JIT flow
GET  /api/auth/oauth/{provider}/callback
```

Drop or stop reading password hashes, local OAuth credentials, and legacy refresh tokens. No environment switch can reactivate these endpoints in production. Unit tests use dependency-injected test principals, not a hidden production login endpoint.

## 8. Identity projection and provisioning

### 8.1 Core models

`Organization` gains `zitadel_org_id`, lifecycle status, and provisioning mode. `User` gains unique `zitadel_user_id` and lifecycle status. `Membership` uses `org_admin | operator | user`, lifecycle status, provisioning source, and confirmed ZITADEL role-assignment identifier.

Add the `ProvisioningOperation`, `OrganizationInvitation`, `IdentityConnection`, and `IdentityEvent` records defined by the related 2026-08-15 design. Every external mutation has an idempotency key, correlation ID, attempt count, sanitized error code, and terminal state.

### 8.2 Organization creation

Only a platform control-plane principal may create an organization. The durable workflow creates the local `provisioning` record, creates the matching ZITADEL organization and project grant, creates a first-admin invitation, persists confirmed identifiers, and activates the organization only when every required step succeeds.

Organization bootstrap also provisions mandatory first-party product defaults transactionally or through explicit resumable steps. It does not create per-organization MCP records for internal services. Internal RAG and other first-party services use platform-managed service configuration; user-managed MCP integrations remain optional organization data.

### 8.3 Invitations and identity matching

- Normalize email and require exact verified-email matching.
- Zero match creates one ZITADEL identity through the provisioning operation.
- One exact verified match reuses the identity.
- Multiple/conflicting matches stop with a security incident.
- Responses do not disclose whether an identity already exists.
- Invitations are single-use, expiring, revocable, and safe to resend.
- Acceptance requires an authenticated subject and verified canonical email matching the invitation target.
- No dry-run migration or discovery path creates real identities.

### 8.4 Lifecycle synchronization

Actions v2 event executions call a signed internal identity-event endpoint. The endpoint verifies payload integrity and timestamp, rejects replayed event IDs, persists the event durably, and acknowledges only after commit. Actions v2 must be explicitly enabled and its target/execution resources managed as code.

A cursor-based Event API poller recovers missed delivery, and a full reconciliation compares ZITADEL organizations, identities, grants, and role assignments with the local projection. Event cursors advance only after successful processing.

Security events target five-second p95 propagation under healthy conditions. Reconciliation runs every 15 minutes; the recovery poll interval is 30 seconds. Missing, conflicting, excessive, or stale projection never raises access and always emits an operator-visible incident.

## 9. Central authorization model

### 9.1 Principal types

```text
PrincipalContext
  principal_type        human | service | platform | support
  principal_id
  organization_id       nullable only for platform control plane
  membership_id         human organization principal
  role                   org_admin | operator | user
  permissions            resolved immutable set for this request
  session_id             human/support
  service_principal_id   service
  support_grant_id       support
```

There is no `select(User).limit(1)` fallback and no implicit default organization. A request without one valid principal fails `401`; a valid principal without the required organization relationship fails closed.

### 9.2 Authorization decision

```text
AuthorizationDecision
  allowed
  permission
  scope                  own | organization | published | platform
  owner_field            model-specific adapter output
  conditions
  denial_code
```

Every protected route declares permission and expected scope metadata. Domain services that cross a trust boundary receive `PrincipalContext`; repositories receive a decision or a centrally produced predicate. Static route coverage fails CI if a protected endpoint lacks explicit metadata.

Direct role comparisons, JWT role authorization, request-state role shortcuts, and hand-written ownership rules are removed after their call-site inventory reaches zero.

### 9.3 Role responsibilities

| Capability | `org_admin` | `operator` | `user` |
|---|---|---|---|
| Members, invitations, roles, SSO, SCIM | Manage | None | None |
| Billing, quotas, organization security | Manage | Read operational limits | Own usage only |
| Agents, workflows, providers, models, MCP | Manage | Manage | Published/read/run only |
| Operational runs and evaluations | Organization | Organization | Own/published where applicable |
| Files and workspace | Organization | Organization | Own unless explicitly shared |
| Approvals | Organization policy | Operational policy | Own request status/eligible consent only |
| Service principals/API keys | Manage | Restricted operational keys | None |
| Organization audit | Full | Operational subset | None |

Platform administration is a separate authority and is never represented as an organization role.

### 9.4 Enforcement surfaces

The same principal resolution and authorization service protects every entry point: HTTP and WebSocket handlers, MCP tools/resources, background workers, schedulers, approval callbacks/resume paths, ingestion callbacks, and internal service endpoints. Internal callers authenticate as narrowly scoped first-party service identities; network location and Docker's internal network are defense in depth, not authentication.

Every persisted asynchronous command carries immutable actor/correlation identifiers and the minimum resource identifiers needed to reload state. A worker must reconstruct a current principal and authorization decision before execution. It must not trust a role, permission set, organization, approval result, or ownership assertion serialized by a client or an earlier request.

Tenant and ownership predicates are applied in the repository query itself wherever practical. Fetching an object globally and checking it afterward is forbidden for customer data because it creates cross-tenant enumeration and accidental disclosure paths.

## 10. Effective agent and tool permission

Runtime permission is computed for every tool call and approval resume:

```text
effective =
    principal role permission
  AND organization policy
  AND agent allowed risk tier
  AND tool's immutable registry risk tier
  AND tool-specific permission
  AND resource scope/ownership
  AND delegation ceiling
```

The existing `evaluate_permission_intersection()` becomes the single evaluator or is replaced by an equivalent typed policy service. Both normal tool execution and resumed approved execution call the same evaluator immediately before side effects.

Delegated agents inherit a permission ceiling from the initiating principal and parent agent. Delegation can only reduce permissions. Queue payloads carry principal/session identifiers, not trusted serialized permission sets; the worker resolves current policy before execution.

Tool risk tier and approval requirements come only from the server-side tool registry and reviewed organization policy. Model output, prompts, tool arguments, or client input cannot lower risk classification.

## 11. Risk-based approval separation of duties

### 11.1 Fixed policy

| Risk/action class | Requirement |
|---|---|
| `safe`, `read` | No approval unless the tool declares explicit user consent |
| `write`, `network` reversible/personal | Requester confirmation may be allowed only when registry policy marks it `self_consent_allowed` |
| `write`, `network` organization-shared or external side effect | Different eligible `operator` or `org_admin` must decide |
| `execute`, `dangerous`, destructive, identity, role, credential, billing | Different eligible principal must decide; dangerous/identity/security requires `org_admin` |

Requester and approver must be different principals whenever separation of duties is required. Comparing role alone is insufficient. Approval cannot grant a permission absent from the requester, agent, tool, or resource decision.

The first Organization Admin may invite a second administrator through the explicit membership-management permission, but a single-admin organization cannot bypass high-risk separation of duties. It must add another eligible administrator before performing actions that require two principals.

Every decision records requester, approver, both principal types/roles, fixed risk classification, resource, reason, correlation ID, policy version, and timestamp.

## 12. File and knowledge ownership

Uploaded files gain an explicit scope:

```text
visibility              personal | organization
created_by_user_id
organization_id
```

- Human user uploads default to `personal` and are owner-scoped.
- `organization` visibility requires `files:share:organization`; users without that permission cannot create or promote shared files.
- Organization Knowledge Base writes always use organization scope and require an organization-shared permission plus the applicable approval policy.
- RAG collections and metadata preserve organization, visibility, and owner identity so retrieval cannot cross scope.
- Existing endpoints cannot infer visibility from collection names or caller role.

Admins/operators may read organization files according to the role matrix; platform administrators have no implicit data-plane access.

## 13. Service principals and product API keys

`ServicePrincipal` belongs to exactly one organization and stores a reviewed fixed permission set. A product API key belongs to exactly one active service principal, stores only a strong hash and prefix, has mandatory expiry, and can be revoked or rotated independently.

Rules:

- Keys never inherit the creator's current or future human role.
- Requested scopes must be a subset of the creator's grantable service scopes.
- Product keys cannot call platform, identity, invitation, role, billing-security, or support-access APIs.
- Every request resolves a service `PrincipalContext`; no synthetic human user is selected.
- Raw keys are shown once and never logged or recoverable.
- Rotation may allow a bounded overlap window; both keys remain individually auditable.
- Organization suspension or service-principal suspension invalidates all child keys.

ZITADEL machine identities used for IAM APIs and internal first-party service credentials are distinct from these product keys.

## 14. Platform and support access

Platform administration uses a dedicated ZITADEL platform role and control-plane routes. It can manage organization lifecycle and provisioning health but cannot read customer chats, files, email, workflows, or run content.

Customer-content support requires the time-limited, two-person `SupportAccessGrant` from the related design. Requester and approver must differ; scope is explicit and read-only by default; maximum duration is one hour; expiry/revocation terminates the support session.

## 15. API and frontend changes

Retain or introduce:

```text
GET  /api/auth/login?organization=<slug>
GET  /api/auth/callback
POST /api/auth/logout
GET  /api/auth/me
POST /api/auth/switch-org

POST /api/platform/organizations
GET  /api/platform/provisioning-operations

GET    /api/orgs/{id}/members
POST   /api/orgs/{id}/invitations
POST   /api/orgs/{id}/invitations/{invite_id}/resend
DELETE /api/orgs/{id}/invitations/{invite_id}
PATCH  /api/orgs/{id}/members/{user_id}/role
POST   /api/orgs/{id}/members/{user_id}/suspend
DELETE /api/orgs/{id}/members/{user_id}

POST /api/internal/identity/events/zitadel
```

The frontend removes `/register`, password fields, legacy OAuth buttons, and local token storage. It redirects unauthenticated users to the organization-aware ZITADEL flow and derives navigation from backend capabilities. Missing navigation never substitutes for backend enforcement.

## 16. Failure handling

| Failure | Required behavior |
|---|---|
| ZITADEL unavailable during login | Fail login with stable temporary error; no local fallback |
| ZITADEL unavailable during provisioning | Durable operation retries; organization/membership remains inactive |
| Valid identity without projection | `403 ACCOUNT_NOT_PROVISIONED` |
| Invalid/expired signature, state, nonce, audience, or PKCE | `401`, security audit, no session |
| Actions event duplicated | Idempotent receipt; no duplicate mutation |
| Actions event lost | Event API poller recovers it |
| Projection conflicts with ZITADEL | Deny affected access and create reconciliation incident |
| Role/member revoked | Revoke affected sessions and deny next request |
| API key scope insufficient | `403` with safe denial code |
| Agent/tool policy uncertain | Deny tool call before side effect |
| Approval requester equals approver where SoD applies | `403 APPROVAL_SEPARATION_REQUIRED` |
| Last active org admin removal/demotion race | Transactional invariant rejects all conflicting mutations |

Error responses expose stable codes and correlation IDs, never tokens, secrets, raw ZITADEL errors, or identity-enumeration details.

## 17. Verification strategy

### 17.1 Static and unit coverage

- Complete role-permission-scope matrix.
- CI route inventory that fails on an unclassified protected route.
- Central scope adapters for every tenant/owner model.
- Effective permission intersection for normal, delegated, queued, and approval-resume execution.
- Fixed risk-to-approval mapping and requester/approver separation.
- File personal/organization scope and RAG metadata enforcement.
- Service principal scope subset, expiry, suspension, rotation, and revocation.
- OIDC claim/state/nonce/PKCE/session/CSRF validation.
- Last-admin invariant under concurrent transactions.
- No imports/call sites for legacy register, password login, refresh, JIT OAuth, global API fallback, or direct role helpers.

### 17.2 Integration tests

- Provisioning operation resumes after each injected external-call failure.
- Invitation reuse/new identity/conflict paths do not enumerate accounts.
- Signed event replay protection and idempotent processing.
- Dropped event recovery through Event API.
- Reconciliation detects missing, excessive, and conflicting assignments.
- Session revocation after user, membership, role, and organization lifecycle events.
- Requests presenting multiple credential types are rejected as ambiguous; credentials are never OR'ed or merged.

### 17.3 Mandatory real ZITADEL E2E

CI and pre-production deploy a real pinned ZITADEL instance; identity SDK/API calls are not mocked. The suite proves:

1. Platform bootstrap and first organization/admin invitation.
2. Authorization Code + PKCE login and logout.
3. Unprovisioned identity denial.
4. Invitation acceptance for new and existing cross-organization identities.
5. Multi-organization switch with session rotation.
6. `org_admin/operator/user` route and ownership matrix.
7. Role change, suspension, deprovisioning, and session revocation.
8. Service-principal API-key scope enforcement.
9. Tool risk intersection and approval SoD.
10. Personal file isolation and organization Knowledge Base access.
11. ZITADEL restart, temporary unavailability, webhook loss, and reconciliation recovery.
12. SMTP invitation delivery through a test sink.

No production account is onboarded until this suite, Docker image builds, backend tests, frontend typecheck/build, and Compose configuration all pass.

## 18. Observability and audit

Metrics include login outcomes, callback validation failures, active/revoked sessions, provisioning latency/retries/dead letters, event delivery lag, reconciliation drift, denied permissions by safe code, approval SoD denials, service-key use/revocation, and organization bootstrap health.

Audit events include actor and principal type, organization, session/service/grant identifier, action, target, old/new values, result, reason, source IP/user-agent hashes, policy version, correlation ID, and timestamp. Raw credentials, authorization codes, cookies, tokens, invitation secrets, and external IdP secrets never enter logs or audit metadata.

Alerts cover sustained login failure, signature validation anomalies, projection lag over SLO, reconciliation drift, provisioning dead letters, last-admin invariant attacks, expired TLS/SMTP/backup checks, and repeated cross-tenant denials.

## 19. Delivery plan and production gate

Implementation is split into mergeable workstreams, but there is no partial production release:

1. **Authorization consolidation:** route inventory, typed decisions, scope adapters, three-role matrix, effective tool intersection, approval SoD, and file ownership.
2. **ZITADEL infrastructure:** pinned Compose/pre-production deployment, bootstrap as code, TLS/SMTP/config/secrets, readiness, metrics, and backup/restore.
3. **Identity projection and provisioning:** schema, durable operations, platform organization creation, invitations, lifecycle events, poller, and reconciliation.
4. **OIDC application sessions:** PKCE callback, opaque session, CSRF, organization switching, frontend login/logout, and capability response.
5. **Service principals and API keys:** scoped principals, rotation/revocation, API/UI, audit, and removal of synthetic-human authentication.
6. **Legacy removal:** registration/password/OAuth-JIT/refresh/global-key code, schemas, routes, UI, configuration, and obsolete data columns/tables.
7. **Production verification:** full unit/integration suite, real ZITADEL E2E, failure injection, security review, restore drill, and deployment smoke.

Each workstream has its own implementation plan and tests. The final release gate requires all seven to be complete. Because there are no production users, rollback before first onboarding is simply redeploying/fixing the unopened system; rollback must never reactivate legacy authentication.

## 20. Acceptance criteria

The product is ready for first production onboarding only when:

1. ZITADEL is the only human authentication path and is pinned/configured for production.
2. Public registration, local password/JWT/refresh/OAuth-JIT, and global API-key fallback are absent.
3. Authentication cannot create an organization, user, membership, or role implicitly.
4. Every protected entry point has explicit permission and enforced resource scope.
5. `org_admin/operator/user` route and ownership tests pass.
6. Agent, delegated task, workflow, approval resume, and product API key cannot exceed their initiating principal.
7. High-risk requester self-approval is impossible.
8. Personal files are owner-isolated and shared knowledge is explicitly organization-scoped.
9. Service API keys have fixed scopes, expiry, revocation, and non-human audit identity.
10. Lifecycle events revoke sessions within the target SLO and reconciliation recovers missed events.
11. Cross-tenant, cross-owner, ambiguous-credential, stale-projection, and last-admin concurrency tests pass.
12. Real ZITADEL E2E and failure injection pass without mocked identity calls.
13. TLS, SMTP, monitoring, alerting, secret management, backup, and restore evidence exist.
14. No production user is invited before the release checklist is signed off.

## 21. Official references

- ZITADEL recommended OIDC/OAuth flows, including Authorization Code + PKCE: <https://zitadel.com/docs/guides/integrate/login/oidc/oauth-recommended-flows>
- ZITADEL production setup: <https://zitadel.com/docs/self-hosting/manage/production>
- ZITADEL Actions v2: <https://zitadel.com/docs/concepts/features/actions_v2>
- ZITADEL Event API: <https://zitadel.com/docs/guides/integrate/zitadel-apis/event-api>
- ZITADEL SCIM v2: <https://zitadel.com/docs/guides/manage/user/scim2>
