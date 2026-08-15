# Enterprise RBAC and ZITADEL Identity Design

Date: 2026-08-15
Status: Approved for implementation planning

## 1. Objective

Replace Open Agent's self-service account creation and two-role authorization model with an enterprise identity and authorization architecture that:

- permits account access only after explicit provisioning;
- uses ZITADEL for authentication, SSO, MFA, invitations, and identity lifecycle;
- separates platform administration from customer-organization administration;
- defines stable organization roles and explicit permissions;
- enforces tenant isolation and object ownership in the application data layer;
- supports a single identity accessing multiple organizations with a distinct role in each;
- fails closed when identity state, role assignment, or synchronization is uncertain.

This design deliberately does not preserve public registration. A successful password, OAuth, OIDC, or SAML authentication is never sufficient to create an Open Agent account or grant organization access.

## 2. Current-state problems

The current application allows `POST /api/auth/register` to create a user, organization, and admin membership. The OAuth callback has equivalent just-in-time creation behavior. This mixes a self-service SaaS identity model with an enterprise-managed product.

The current RBAC model also has these shortcomings:

- only `admin` and `user` exist, so routine operation and identity administration cannot be separated;
- some user-visible resources are organization-scoped but not owner-scoped;
- role checks, ownership filters, and route behavior are not expressed through one authorization decision;
- legacy `owner`, `developer`, and `viewer` defaults remain in parts of the authentication code;
- local password, JWT, refresh-token, OAuth, and membership lifecycle responsibilities are implemented by Open Agent itself.

## 3. Architectural decision

Use ZITADEL as the enterprise identity platform. Open Agent remains responsible for domain authorization and resource ownership.

### 3.1 ZITADEL responsibilities

- Interactive authentication through OIDC Authorization Code with PKCE.
- Local credential lifecycle where enabled.
- External OIDC and SAML identity-provider federation.
- MFA, passkeys, recovery, lockout, and authentication policy.
- Invitation, email verification, and account initialization.
- SCIM provisioning and deprovisioning.
- Human users, service accounts, organization identity policy, and project role assignments.
- Identity and authentication audit events.

### 3.2 Open Agent responsibilities

- Product organizations and their business state.
- Domain permission matrix and scope resolution.
- Tenant isolation and object ownership.
- Agent, tool, approval, quota, and resource policies.
- Business audit events.
- Projection of ZITADEL identity and role-assignment state for request-time enforcement.
- Platform and organization administration surfaces.

ZITADEL is the system of record for credentials, identity status, and project role assignments. Open Agent is the system of record for product data, ownership, and business policy. Open Agent's membership table is a fail-closed enforcement projection, not an independent competing role source.

## 4. ZITADEL structure

One ZITADEL instance contains:

```text
ZITADEL instance
├── Platform organization
│   └── OpenAgent project
│       ├── Web OIDC application
│       ├── API/service application
│       └── project roles: org_admin, operator, user
├── Customer organization A
│   ├── users and service accounts
│   ├── organization-specific IdPs and login policy
│   └── grant for the OpenAgent project
└── Customer organization B
    ├── users and service accounts
    ├── organization-specific IdPs and login policy
    └── grant for the OpenAgent project
```

Each Open Agent organization maps one-to-one to a ZITADEL customer organization. The Platform organization owns the OpenAgent project and grants its roles to customer organizations.

A ZITADEL user normally has one home organization. The same identity may access another Open Agent organization through an external project role assignment. Open Agent still represents this as a distinct membership for each product organization.

End users do not receive access to the ZITADEL Management Console. Open Agent administration APIs call ZITADEL management APIs with narrowly scoped service identities.

## 5. Authority hierarchy

### 5.1 Platform Admin

`platform_admin` is an instance/control-plane authority outside customer-organization RBAC. It may:

- create, suspend, reactivate, and archive product organizations;
- create the first Organization Admin invitation;
- manage platform policy and subscription state;
- inspect provisioning-operation health.

A Platform Admin does not automatically receive access to customer chats, files, email, workflows, or run content. Customer-data access requires a separate, time-limited break-glass grant with reason, approval, expiry, revocation, and audit.

### 5.2 Organization roles

Open Agent defines three fixed roles for the initial release:

- `org_admin`: organization identity, security, membership, billing, configuration, and data administration;
- `operator`: product configuration and operation without identity, role, billing, or organization-security administration;
- `user`: consumption of published product capabilities with personal data scope.

Custom roles are excluded from the initial release. Fixed roles keep the permission model reviewable and make route coverage testable. The data model and permission evaluator must not assume that role names are encoded into resource queries, so custom roles can be added later without redesigning ownership enforcement.

## 6. Permission and scope model

An authorization decision is not a Boolean role check. It contains an action and an enforced data scope:

```text
AuthorizationDecision
├── allowed: bool
├── permission: resource:action
├── scope: own | organization | published | platform
└── conditions: structured policy conditions
```

Examples:

```text
agents:read             scope=published
sessions:read           scope=own
workflow_runs:read      scope=organization
memberships:manage      scope=organization
organizations:create    scope=platform
```

Repositories or centralized query-policy helpers must apply the resulting scope. A route handler must not be responsible for remembering whether a query needs `created_by_user_id`, `requested_by`, `triggered_by_user_id`, or another ownership predicate.

### 6.1 High-level role matrix

| Capability | `org_admin` | `operator` | `user` |
|---|---|---|---|
| View organization profile | Organization | Organization | Organization basics |
| Manage members, invitations, and roles | Yes | No | No |
| Configure SSO, SCIM, and security policy | Yes | No | No |
| Manage agents and workflows | Yes | Yes | No |
| Manage providers, models, MCP, and integrations | Yes | Yes | No |
| Publish agents and workflows | Yes | Yes | No |
| Run published capabilities | Yes | Yes | Yes |
| Read operational runs | Organization | Organization | Own |
| Read workspace and files | Organization | Organization | Own |
| Read usage | Organization | Organization | Own |
| Configure quotas | Yes | No | No |
| Read audit | All organization audit | Operational subset | No |
| Manage service accounts/API credentials | Yes | Limited operational credentials | No |
| Billing and subscription | Yes | No | No |

### 6.2 Effective permission

Tool and agent execution uses the intersection of all applicable policies:

```text
effective permission =
    user permission
  ∩ organization policy
  ∩ agent capability
  ∩ tool risk policy
  ∩ resource scope and ownership
```

No agent identity, delegated task, API key, or workflow can elevate the calling principal beyond this intersection.

## 7. Approval separation of duties

- A principal may not approve a dangerous action it requested.
- A user may read only its own approval requests and statuses.
- Operators and Organization Admins may decide requests submitted by another principal.
- Organization policy may require an Organization Admin for high-risk actions.
- Approval permission does not bypass agent capability, tool risk, quota, tenant, or ownership policy.
- Every decision records requester, approver, role, decision, reason, resource, correlation ID, and timestamp.

## 8. Data model

### 8.1 Organization

Add or retain:

```text
id
zitadel_org_id              unique, non-null after provisioning
name
slug                         unique
status                       provisioning | active | suspended | archived
provisioning_mode            invitation | sso | scim
created_by_platform_admin_id
created_at
updated_at
```

### 8.2 User

```text
id
zitadel_user_id              unique
email
display_name
status                       invited | active | locked | deactivated
created_at
updated_at
```

Open Agent does not store password hashes, password-reset secrets, MFA secrets, or ZITADEL refresh tokens.

### 8.3 Membership

```text
id
organization_id
user_id
role                         org_admin | operator | user
status                       pending | active | suspended | revoked
provisioning_source          invitation | sso | scim | platform
zitadel_role_assignment_id
invited_by_membership_id
created_at
updated_at
unique(organization_id, user_id)
```

### 8.4 Identity connection

```text
id
organization_id
type                         oidc | saml
zitadel_idp_id
verified_domains
provisioning_policy
enabled
created_at
updated_at
```

Secrets remain in ZITADEL or a secret manager and are not returned through Open Agent APIs.

### 8.5 Provisioning operation

```text
id
organization_id              nullable for organization creation
operation_type
idempotency_key              unique per operation type
status                       pending | processing | succeeded | failed
attempts
last_error_code
last_error_detail_redacted
correlation_id
created_at
updated_at
```

### 8.6 Support access grant

```text
id
organization_id
platform_admin_id
reason
approved_by_platform_admin_id
expires_at
revoked_at
created_at
```

## 9. Provisioning flows

### 9.1 Create an organization

```text
Platform Admin request
→ create local organization as provisioning
→ create ZITADEL organization
→ grant OpenAgent project and allowed roles
→ create first Organization Admin identity/invitation
→ create pending local user and membership projections
→ send invitation
→ persist confirmed ZITADEL identifiers
→ mark organization active
```

The workflow is idempotent and resumable. An organization does not become active until all required ZITADEL resources and the first Organization Admin invitation are confirmed.

### 9.2 Invite a member

```text
Organization Admin chooses email and role
→ validate admin authority and organization state
→ create provisioning operation
→ create or locate eligible ZITADEL identity
→ create project role assignment
→ send single-use, expiring invitation
→ create pending local projection
→ activate projection after invitation/identity confirmation
```

Resending invalidates the previous invitation token. Revocation prevents completion of an outstanding invitation.

### 9.3 SSO authentication

```text
Browser
→ Open Agent login endpoint with organization hint
→ ZITADEL Authorization Code + PKCE
→ organization-specific external IdP when configured
→ backend callback validates state, nonce, issuer, audience, signature, and expiry
→ backend resolves ZITADEL subject
→ backend requires active local user, membership, and organization projection
→ backend creates an organization-bound application session
```

An authenticated identity without an active provisioned membership receives `403 ACCOUNT_NOT_PROVISIONED`. The callback never creates a user, organization, membership, or role assignment.

### 9.4 SCIM

- IdP groups map explicitly to one of the three roles.
- An unmapped group grants no Open Agent membership.
- Deactivation or removal revokes membership and application sessions.
- Conflicting role mappings fail closed and create a security event.
- SCIM-managed role assignments are changed through the upstream directory, not manually in Open Agent, unless the connection policy explicitly transfers ownership back to manual provisioning.

## 10. Synchronization and failure handling

Identity mutations use a durable provisioning operation instead of an uncontrolled dual write:

```text
requested
→ ZITADEL mutation confirmed
→ local enforcement projection applied
→ succeeded
```

Retries reuse the same idempotency key. Errors expose stable, non-sensitive error codes. A reconciliation job periodically compares ZITADEL identities and role assignments with local projections.

Rules:

- uncertainty never raises access;
- missing or stale projection denies access;
- a local role may not exceed the confirmed ZITADEL role assignment;
- ZITADEL unavailability blocks identity mutations but does not invalidate already verified active application sessions unless policy requires online verification;
- suspend, revoke, role change, and SCIM deprovision events revoke affected sessions immediately after confirmation;
- drift creates a security audit event and an operator-visible reconciliation incident.

## 11. Session security

- Use OIDC Authorization Code with PKCE.
- The browser does not store ZITADEL tokens in local storage.
- The backend exchanges the authorization code and issues an opaque application session.
- Session cookies are `HttpOnly`, `Secure`, and appropriately `SameSite` protected.
- State-changing cookie-authenticated requests require CSRF protection.
- Sessions bind to an active organization and principal.
- Organization switching rotates the application session after confirming an active membership.
- Role changes, suspension, deactivation, and membership revocation invalidate affected sessions.
- Backend authorization uses current membership projection; it does not trust a role claim in a long-lived browser token as the final decision.

## 12. API surface

### 12.1 Authentication

Retain or introduce:

```text
GET  /api/auth/login?organization=<slug>
GET  /api/auth/callback
POST /api/auth/logout
GET  /api/auth/me
POST /api/auth/switch-org
```

Remove:

```text
POST /api/auth/register
POST /api/auth/login using application-owned passwords
POST /api/auth/refresh using application-owned refresh tokens
```

### 12.2 Platform control plane

```text
POST /api/platform/organizations
GET  /api/platform/organizations
POST /api/platform/organizations/{id}/bootstrap-admin
POST /api/platform/organizations/{id}/suspend
POST /api/platform/organizations/{id}/reactivate
GET  /api/platform/provisioning-operations
```

### 12.3 Organization identity administration

```text
GET    /api/orgs/{id}/members
POST   /api/orgs/{id}/invitations
POST   /api/orgs/{id}/invitations/{invite_id}/resend
DELETE /api/orgs/{id}/invitations/{invite_id}
PATCH  /api/orgs/{id}/members/{user_id}/role
POST   /api/orgs/{id}/members/{user_id}/suspend
DELETE /api/orgs/{id}/members/{user_id}
GET    /api/orgs/{id}/identity-connections
POST   /api/orgs/{id}/identity-connections
GET    /api/orgs/{id}/audit
```

Required invariants:

- the last active Organization Admin cannot be removed, suspended, or demoted;
- a principal cannot elevate its own role;
- SCIM-owned assignments cannot be changed through the manual endpoint;
- invitation and role mutations require explicit target organization checks;
- all mutations are audited.

## 13. User interfaces

Open Agent exposes three distinct surfaces:

1. Platform Console: organization lifecycle, first-admin bootstrap, provisioning health, and break-glass grants.
2. Organization Administration: members, invitations, roles, identity connections, SCIM, security policy, billing, and organization audit.
3. Product Workspace: agents, workflows, integrations, chat, files, approvals, and usage according to role and resource scope.

Operators do not see Members, Identity, Security, or Billing. Users see only published/consumption surfaces and their own data. The `/register` route and all self-registration calls are removed.

## 14. Migration and cutover

1. Deploy and harden ZITADEL, SMTP, monitoring, backup, and service identities.
2. Create the Platform organization and OpenAgent project.
3. Create a ZITADEL customer organization for every existing Open Agent organization.
4. Provision existing users and persist identity mappings.
5. Map existing roles: `admin → org_admin`, `user → user`.
6. Have Organization Admins review and demote routine operators from `org_admin` to `operator`.
7. Activate users through invitation or customer SSO; do not reuse application-owned passwords.
8. Run projection reconciliation and dual-read verification before cutover.
9. Switch authentication to ZITADEL and revoke all legacy JWTs and refresh tokens.
10. Remove register UI/API and just-in-time OAuth account creation.
11. Retain a time-bounded rollback path that does not reopen self-registration.
12. After the rollback window, remove legacy password hashes, refresh-token records, and obsolete auth configuration.

Authorization has one effective source in each migration phase. Legacy and ZITADEL roles are never unioned.

## 15. Audit requirements

Audit events include actor, actor type, organization, target, action, old/new values where applicable, result, reason, IP, user agent, correlation ID, and timestamp.

Mandatory events include:

- organization create, suspend, reactivate, and archive;
- first-admin bootstrap;
- invitation create, resend, revoke, accept, and expire;
- role assignment and removal;
- member suspend, reactivate, and revoke;
- SSO/SCIM connection changes;
- SCIM provision and deprovision;
- session revocation;
- provisioning failure and reconciliation drift;
- break-glass request, approval, use, expiry, and revocation;
- approval decisions and high-risk tool execution.

Sensitive secrets and raw tokens are never written to audit metadata.

## 16. Verification and acceptance criteria

### 16.1 Authentication and provisioning

- Registration endpoints and UI no longer exist.
- Local login, OAuth, OIDC, or SAML cannot create an account implicitly.
- A valid external identity without provisioning receives `ACCOUNT_NOT_PROVISIONED`.
- Invitation tokens are single-use, expiring, revocable, and safely resendable.
- Provisioning retries do not create duplicate organizations, users, or assignments.

### 16.2 Authorization

- Every protected route has an explicit permission and scope.
- Cross-organization access is denied.
- Cross-user access to sessions, messages, tasks, chat runs, workflow runs, files, approvals, and usage is denied for `user`.
- The complete `org_admin`/`operator`/`user` matrix has route-level regression coverage.
- An agent, API key, service account, or delegated task cannot elevate its caller.
- The last Organization Admin invariant is enforced under concurrent requests.

### 16.3 Lifecycle and resilience

- Role change, suspension, membership revocation, and SCIM deprovision revoke access.
- ZITADEL unavailability fails identity mutations closed.
- Reconciliation detects missing, excessive, and conflicting role assignments.
- No drift path automatically elevates a role.
- Organization provisioning resumes safely after partial failure.

### 16.4 Security

- OIDC state, nonce, issuer, audience, signature, expiry, and PKCE are verified.
- Tokens do not persist in browser local storage.
- Session cookies and CSRF controls are verified by integration tests.
- Platform Admin has no implicit customer data-plane access.
- Break-glass grants expire automatically and cannot cross organization scope.
- Audit records contain required context and never contain credentials.

## 17. Operational requirements

A production self-hosted ZITADEL deployment requires PostgreSQL, TLS, SMTP, secrets management, backups with restore testing, monitoring, and controlled upgrades. High-availability environments separate initialization, setup/migration, and runtime workloads and run multiple application replicas behind an HTTP/2-capable proxy.

ZITADEL configuration is managed as code. Default and organization policies explicitly disable self-registration. Every external IdP disables automatic account creation unless a future approved provisioning mode intentionally enables it.

## 18. Explicit non-goals

- Public or domain-only self-registration.
- Just-in-time account or membership creation in an authentication callback.
- User-defined custom roles in the first release.
- Storing passwords, MFA secrets, or external IdP secrets in Open Agent.
- Granting Platform Admin implicit access to customer content.
- Treating frontend navigation visibility as authorization enforcement.
- Trusting a stale role claim without current organization and membership validation.

## 19. References

- ZITADEL B2B scenario: <https://zitadel.com/docs/guides/solution-scenarios/b2b>
- ZITADEL organizations: <https://zitadel.com/docs/guides/manage/console/organizations-overview>
- ZITADEL projects and role assignments: <https://zitadel.com/docs/guides/manage/console/projects-overview>
- ZITADEL login policy: <https://zitadel.com/docs/guides/manage/console/default-settings>
- ZITADEL external OIDC provider configuration: <https://zitadel.com/docs/guides/integrate/identity-providers/generic-oidc>
- ZITADEL SCIM: <https://zitadel.com/docs/guides/manage/user/scim2>
- ZITADEL production setup: <https://zitadel.com/docs/self-hosting/manage/production>
