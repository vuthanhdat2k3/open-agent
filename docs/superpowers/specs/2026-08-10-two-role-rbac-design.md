# Two-Role RBAC (User / Admin) — Design Spec

Date: 2026-08-10
Status: Approved and implemented, live-verified

## 1. Context

The product previously ran a 4-role model (`owner/admin/developer/viewer`)
with a fairly complete permission matrix (`backend/app/core/authz/policy.py`).
The user asked for a simpler, product-ready split into exactly 2 roles —
**user** (consumes the product) and **admin** (configures/operates it) —
with one specific, explicit constraint: in Chat, a `user` must not be able to
switch agents. Once multi-agent orchestration is standardized, a user only
ever talks to the org's primary agent, may choose an admin-configured model,
or supplies input to a published workflow.

## 2. Feature → role mapping

| Feature | User | Admin |
|---|---|---|
| Chat | Chats with the org's primary (`kind=orchestrator`) agent only; may switch among active admin-configured models | Full — any agent, any model |
| Agents (builder) | No access | Full |
| Workflows (builder) | No access | Full |
| Workflows (run) | Can run published workflows (`workflows:run` retained) | Full |
| MCP Servers / Models / Providers / Integrations | No access | Full |
| Workspace | Own data (nav item visible to both; ownership-scoped filtering is a follow-up, see §5) | Full |
| Files (RAG ingestion) | Read-only | Full |
| Approvals | Read own status; cannot decide (four-eyes control preserved) | Read + decide |
| Evaluations | No access | Full |
| Quotas | Read own usage | Read + manage |
| Members / Debug | No access | Full |

## 3. Implementation

**Backend**
- `app/models/role.py`: `Role` enum collapsed to `admin`/`user`.
- `app/core/authz/policy.py`: `PERMISSIONS` matrix rewritten — `admin: {"*"}`,
  `user` gets the narrow explicit set from the table above.
- `app/models/membership.py`: `role` column changed from a native Postgres
  `Enum(Role)` to `Enum(Role, native_enum=False, length=32)` — plain
  `VARCHAR`, Role validation stays at the Python layer. Required because the
  DB migration drops the old native enum type entirely (see below); leaving
  the model declared as a native enum made SQLAlchemy emit `::role` casts
  against a type that no longer exists, breaking every membership insert.
- `alembic/versions/0025_two_role_rbac.py`: data-migrates existing rows
  (`owner→admin`, `developer|viewer→user`) and converts the column type,
  handling Postgres (drop the native enum type) and SQLite (batch rebuild)
  separately. Downgrade is documented as lossy/best-effort — the 4-way
  distinction can't be reconstructed from 2 roles.
- `agents.py`'s `list_agents` route: when the caller isn't admin, filters the
  response to `kind="orchestrator"` agents only — this is the actual
  enforcement point for "user can't pick a worker agent," not just a UI
  hide, since the data itself is restricted.
- Org creation / registration (`auth.py`, `orgs.py`): the org creator becomes
  `admin` (previously `owner`); member invites accept `admin`/`user`,
  default `user`.
- `core/authz/scope.py` stores the authenticated ownership scope on the
  request-scoped `AsyncSession`. Workspace, approval, and quota services use
  that shared scope so `user` queries are filtered by their creator/requester
  column while `admin` queries remain organization-wide.
- Agent/workflow execution now attributes messages, usage events, workflow
  runs, tool contexts, approval requests, sub-workflows, and detached jobs to
  the caller. This gives ownership filtering a stable actor identity instead
  of incorrectly inheriting the agent/workflow creator.

**Frontend**
- `types/index.ts`, `useCurrentRole()` (new hook in `hooks/index.ts`):
  resolves the caller's role for the active org, failing closed to `"user"`
  if unresolved.
- `navigation.ts`: `NavItem.adminOnly` flag marks Agents/Workflows/MCP/
  Integrations/Models/Providers/Evaluations/Members/Debug; `app-sidebar.tsx`
  filters the rendered menu by role (defense-in-depth UI hide — the backend
  already enforces the real permission on every route).
- `chat-header-controls.tsx` / `chat-thread.tsx`: the agent dropdown remains
  locked to a plain label for users, while the model dropdown is available for
  active admin-configured models. Session switching stays fully functional.
- `/run-workflow` is the lightweight user surface: choose an existing
  workflow, enter input, run it, then review the reused workflow console's
  live node log and final output. The admin builder remains at `/workflows`.
- Workspace and Approvals retain read-only controls for `user`; Quotas shows
  only personal monthly cost/storage usage. Admin-only controls and queries
  are not rendered or fetched. The Dashboard workflow CTA also routes users
  to `/run-workflow` and avoids admin-only resource requests.

## 4. Verification

- Backend: 220/220 tests passing (rewrote `test_authz.py`'s permission-matrix
  tests for the 2-role model; fixed 8 other test files' role fixtures/
  assertions that assumed the old 4-role semantics).
- Migration: dry-run against a throwaway SQLite DB with all 4 old role
  values present, both upgrade and downgrade paths, before touching the real
  database. Applied to the real (Supabase Postgres) database via
  `alembic upgrade head` after confirming existing membership rows.
- **Live bug found via this verification, not caught by tests**: the register
  endpoint 500'd after migrating (`type "role" does not exist`) because the
  ORM model still declared a native Postgres enum column pointing at a type
  the migration had just dropped. Fixed per §3; re-verified register works.
- Full end-to-end role check in the browser: registered a throwaway account,
  invited it into the real org as `user` via the real Members UI, logged in
  as that account, switched org context, and confirmed the sidebar shows
  only Dashboard/Chat/Workspace/Files/Approvals/Quotas, and Chat's header
  shows a static "Assistant" agent label alongside the model dropdown (only
  the agent selector is locked; session switching remains interactive). Test account and membership
  cleaned up afterward.

## 5. Follow-up completed on 2026-08-10

- Ownership-scoped Workspace/Approvals/Quotas filtering is implemented at
  the shared service/query layer, including correct caller attribution for
  agent and workflow execution paths.
- The simplified user-only Run Workflow surface is implemented and reuses
  the existing workflow console rather than duplicating execution UI.
- Docker live verification used frontend `:3000`, API `:8000`, and the real
  Postgres-backed stack. A temporary `user` ran deterministic workflow
  `2d651d59-86c8-4fc5-a20d-f96533ff7300`; run
  `6fc0d165-284f-48cc-919f-d3912f07834a` succeeded with exact output
  `RBAC_DOCKER_ECHO_FE55C5AD`, and `triggered_by_user_id` matched the caller.
  The temporary users, memberships, workflow, and run were removed afterward.
- Browser checks covered both roles: the user received the runner and
  read-only/personal Workspace, Approvals, and Quotas views with no forbidden
  Dashboard requests; the admin retained builder/navigation and quota policy
  controls. The runner was also checked at a 375×812 viewport.
- Regression coverage includes mixed-owner Workspace artifacts/executions,
  approvals, usage, agents, workflows, and files for both roles. The complete
  backend suite passes: **245 passed**.

## 6. User model switching completed on 2026-08-10

- `ChatRequest.model_id` is now a per-chat model override. User requests are
  validated against the active organization and `Model.active`; cross-org and
  inactive selections are rejected without changing the orchestrator default.
- Admin model selection keeps the existing agent-default/release behavior.
- Backend suite passes: **245 passed**. Frontend typecheck and Docker
  production build pass.
- Docker live test with `user@openagent.com` selected `Qwen 3.6 fast` and
  received exact response marker `USER_MODEL_SWITCH_OK`; the resulting usage
  event recorded the selected model and the user as owner.

## 7. Still out of scope

- Telegram/X/Facebook search integrations (from the earlier web-search work)
  remain out of scope, unrelated to this change.
