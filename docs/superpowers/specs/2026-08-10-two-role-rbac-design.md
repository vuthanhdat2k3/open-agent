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
ever talks to the org's primary agent, or supplies input to a published
workflow.

## 2. Feature → role mapping

| Feature | User | Admin |
|---|---|---|
| Chat | Chats with the org's primary (`kind=orchestrator`) agent only — no agent/model switcher | Full — any agent, any model |
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

**Frontend**
- `types/index.ts`, `useCurrentRole()` (new hook in `hooks/index.ts`):
  resolves the caller's role for the active org, failing closed to `"user"`
  if unresolved.
- `navigation.ts`: `NavItem.adminOnly` flag marks Agents/Workflows/MCP/
  Integrations/Models/Providers/Evaluations/Members/Debug; `app-sidebar.tsx`
  filters the rendered menu by role (defense-in-depth UI hide — the backend
  already enforces the real permission on every route).
- `chat-header-controls.tsx` / `chat-thread.tsx`: agent and model dropdowns
  render as plain non-interactive labels when `canSwitchAgent` is false
  (role !== admin); session switching stays fully functional for everyone.

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
  shows a static "Assistant" label with no agent/model dropdown (only the
  session switcher remains interactive). Test account and membership
  cleaned up afterward.

## 5. Explicitly deferred (not built in this pass)

- **Ownership-scoped data filtering**: Workspace/Approvals/Quotas currently
  gate by role only (nav item visible, backend permission granted) — they do
  not yet filter query results to "rows created by this user" vs. the whole
  org. The permission layer is in place; the query-level scoping is a
  follow-up.
- **Simplified "Run Workflow" UI for users**: `workflows:run` is granted to
  `user`, but there is no user-facing surface yet distinct from the full
  admin workflow builder canvas. A lightweight input-only trigger UI is a
  separate, real net-new feature, not part of this RBAC pass.
- Telegram/X/Facebook search integrations (from the earlier web-search work)
  remain out of scope, unrelated to this change.
