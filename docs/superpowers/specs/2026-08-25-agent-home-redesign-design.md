# Spec — Agent Home Redesign (Consolidate page-per-feature into Agent-centric surfaces)

**Date:** 2026-08-25
**Status:** Draft — awaiting user review
**Owner:** Sisyphus
**Scope:** Frontend UX/IA redesign for OpenAgent AgentOS v2 (full rewrite, no Phase 1 stepping). Touches `frontend/`, new backend endpoint `/api/activity/feed` and `/api/events/stream`. Does not modify core agent/workflow engine semantics.

---

## 1. Vision & Goals

### 1.1 Problem statement

OpenAgent currently has **27 routes** in `frontend/app/`. The "automation-leaning" routes (`/email-intelligence`, `/automations`, `/customer-intelligence`) each carry their own full page, and an end-user must navigate into 3 separate pages to know what their agents are doing. The current Dashboard (`app/page.tsx:20`) is a **static stat board**, not a live view.

The product name and architecture say "multi-agent OS" but the UI behaves like "AI toolkit with many sections." This gap is the primary problem.

### 1.2 Goal (one sentence)

> Reorganize the OpenAgent UI so that **end-users land on a single agent-centric Home** where their agents proactively surface activity, while **operators (org_admin / platform_admin) land on a Builder** with full visibility into all resources, all behind a shared shell that supports in-context drawers (not page navigations) for detail views.

### 1.3 Non-goals (this spec)

- Not changing agent execution semantics, the workflow DAG engine, or RBAC permission matrix.
- Not adding new LLM providers, models, or new MCP servers.
- Not introducing new product features (e.g. no new "calendar intelligence" agent).
- Not migrating the data layer (OutboxEvent, TaskTree, CustomerIntelligence tables stay as-is).
- Not a visual-only redesign — IA and data-flow changes are in scope.

### 1.4 Success criteria

| # | Criterion | How verified |
|---|---|---|
| S1 | A `member` role user never needs to open more than 2 pages to complete any common task (e.g. "see why an email was flagged and reply to it"). | E2E click-path test on the 5 most common user journeys. |
| S2 | Real-time event appears on Home within **≤ 2 s** of backend emission. | Synthetic SSE injection + browser perf timing. |
| S3 | Home page LCP ≤ 1.5 s on cable; Activity Feed stream adds ≤ 50 KB/min baseline bandwidth per session. | Lighthouse + Chrome devtools throttling. |
| S4 | `org_admin` can reach any builder surface in ≤ 1 click from `/builder`. | Manual checklist. |
| S5 | All 16+ existing routes continue to function via direct URL during the migration window (graceful deprecation, no broken links). | Build + integration test sweep. |
| S6 | WCAG 2.2 AA contrast and full keyboard navigation preserved; `prefers-reduced-motion` neutralizes all new ambient animations. | axe + manual test. |

---

## 2. Information Architecture (new route map)

### 2.1 Role-based landing

| Role | Default landing | Why |
|---|---|---|
| `member`, `developer`, `viewer` | `/home` (new) | End-user first; the agent is the entry point. |
| `org_admin` | `/builder` (new) | Operator first; they manage resources, not just consume them. |
| `platform_admin` | `/builder/orgs` (new) | Cross-tenant visibility — org list is the operator's "home". |

The landing decision is server-driven: the existing `auth.py` callback already returns the user's role in the session, so `/` becomes a redirect to one of the three based on the highest-privileged role on the active session.

### 2.2 Route map (new vs. existing)

**New routes (5):**
- `GET /home` — End-user Agent Home (replaces `/` for non-operators).
- `GET /builder` — Operator dashboard (cards for Agents/Workflows/Models/Providers/MCP/Integrations + Usage + Approvals queue).
- `GET /builder/agents`, `…/workflows`, `…/models`, `…/providers`, `…/integrations`, `…/mcp` — re-served under `/builder/*` to keep operator resources grouped.
- `GET /builder/orgs` — Platform-admin org switcher (was `/organizations`).

**Kept routes (operator-only, builder scope):**
- `/agents/[id]/edit` — Agent builder (DAG editor + system-prompt form).
- `/workflows/[id]/edit` — Workflow canvas editor.
- `/chat` — Full chat experience, but no longer the default landing for end-users; it is reachable from Home's center panel and from sidebar.
- `/debug` — Advanced debug surface (data-density, kept full-page).
- `/evaluations` — Evaluation runs.
- `/admin/email-intelligence` — Admin Email Ops (already admin-only).
- `/settings/quotas`, `/settings/members`, `/settings/api-keys`.

**Routes that become Drawer-triggered (still mounted, but no longer top-nav entries):**
- `/email-intelligence` → `Activity Feed` filter + detail **Drawer** on Home.
- `/customer-intelligence` → `Activity Feed` filter + detail **Drawer** on Home.
- `/approvals` → `Notification Inbox` item opens approval **Drawer** (full-screen on mobile).
- `/run-workflow` → Builder `/workflows/[id]/run` modal or Home quick-action.

**Routes that become part of Builder, lose their own sidebar item:**
- `/automations` → lives under `/builder/automations` (catalog + active list).
- `/files`, `/workspace` → moved to `UserNav` profile menu (drop "Files"/"Workspace" from sidebar; access via avatar menu or `Cmd+K`).

### 2.3 Sidebar (left nav) — slimmed down

```
[OpenAgent]   [Org Switcher]
─────────────────────────────
  Home           (end-user)
  Builder        (operator)
  Chat
  ──────
  Automations    (operator)
  Integrations   (operator)
  Approvals      (with badge, if any)
  ──────
  Settings
  Help
─────────────────────────────
[Avatar] [Theme] [Sign out]
```

Anything not listed remains reachable by direct URL or `Cmd+K` command palette (out of scope for this spec; v2 follow-up).

---

## 3. Component Breakdown

### 3.1 Shell changes (`components/layout/`)

- **`AppShell`** — add a `mode: "end-user" | "operator"` prop; pass from server-rendered `<body data-mode>` so it survives SSR.
- **`AppSidebar`** — receives the mode and renders the matching nav group list (see 2.3). Mode-conditional: end-user sees "Home / Chat / Approvals" only; operator sees the full builder group.
- **`AppHeader`** — keep, add a slot for `<AgentStatusPill />` (live mini avatar + state) between title and theme toggle.

### 3.2 New: `Home` (end-user surface)

Three-column workspace, fills viewport on `lg+`, collapses to tabs on mobile.

```
┌─────────────────────────────────────────────────────────────────┐
│  [AgentStatusPill] (sticky, ambient)                  [🔔][👤]  │
├──────────────┬──────────────────────────┬────────────────────────┤
│              │                          │                        │
│  Activity    │     Center: Agent        │  Quick Glance          │
│  Feed        │     Composer + Thread    │  (right rail)          │
│  (left)      │     (center)             │                        │
│              │                          │                        │
│  • Today     │  ┌────────────────────┐  │  Today:                │
│  • Email ★   │  │  [Agent Avatar 56] │  │   3 new emails         │
│  • Approvals │  │  Atlas — Online    │  │   1 approval pending   │
│  • Workflows │  │                    │  │   2 workflow runs done │
│  • Runs      │  │  [Composer textarea]│  │                        │
│  • Calendar  │  │                    │  │  Recent files          │
│  • Releases  │  │  [Send] [Voice]    │  │  Recent agents         │
│              │  └────────────────────┘  │  Recent workflows      │
│              │                          │                        │
│              │  Conversation thread     │                        │
│              │  (existing /chat)        │                        │
│              │                          │                        │
└──────────────┴──────────────────────────┴────────────────────────┘
```

**Component tree:**

```
<Home>                                    // frontend/app/home/page.tsx
├── <AgentStatusPill />                   // sticky top-right ambient widget
│   └── <AgentSelector />                 // Popover; lists all org agents; one-tap switch
├── <ActivityFeed>                        // left, 320px on lg+
│   ├── <ActivityFeedFilters />           // tabs: All / Email / Calendar / Approvals / Workflows / Runs
│   ├── <ActivityFeedList />              // virtualized list
│   │   └── <ActivityItem /> × N          // one per event
│   ├── <ActivityFeedSSEController />     // hidden; opens /api/events/stream
│   └── <ActivityFeedEmpty />
├── <AgentChatPanel>                      // center, flex-1
│   ├── <AgentAvatar size="lg" />         // 56px persona
│   ├── <AgentThread>                     // existing ChatThread, scoped to selected agent
│   └── <ChatComposer>                    // existing ChatComposer (docked variant)
└── <QuickGlance>                         // right, 280px on lg+
    ├── <GlanceSection title="Today" />
    ├── <GlanceSection title="Recent files" />
    ├── <GlanceSection title="Recent agents" />
    └── <GlanceSection title="Recent workflows" />
```

### 3.3 New: `ActivityFeed`

**Props:** `{ orgId, userId, mode: "drawer" | "page" }` — same component, mounted both on `/home` and inside the `<NotificationInbox>` drawer.

**Data source:** `useActivityFeed()` hook → `GET /api/activity/feed?cursor=…&limit=50&kinds=email,calendar,workflow_run,approval,agent_run`.

**Live updates:** `useEventStream('/api/events/stream', { onEvent: prepend })` — when an event of a kind the user is viewing arrives, optimistically prepend; otherwise bump the unread badge in `ActivityFeedHeader`.

**`<ActivityItem>`** is a polymorphic card whose body is decided by `event.kind`:

| Kind | Icon | Body | Primary action |
|---|---|---|---|
| `email_received` | envelope | sender, subject, AI summary (if available) | "Open in drawer" → email detail drawer |
| `email_flagged` | shield | sender, flag reason | "Review" → email detail drawer (right rail) |
| `calendar_event_upcoming` | calendar | event title, time, attendees | "View" → calendar detail drawer |
| `approval_required` | shield-check | tool, risk level, agent name | "Review" → approval drawer |
| `workflow_run_started` | workflow | workflow name, trigger | "View run" → workflow-run drawer |
| `workflow_run_completed` | workflow-check | workflow name, duration, status | "View result" |
| `workflow_run_failed` | alert-triangle | workflow name, error excerpt | "Open in Debug" |
| `agent_release_published` | rocket | agent name, version | "View" → agent detail drawer |
| `quota_warning` | gauge | quota type, % used | "Open Quotas" |
| `integration_error` | plug | provider, error | "Reconnect" |

**Drawer trigger:** clicking any item opens `<ActivityDetailDrawer eventId={…} kind={…} />` over the current view (no route change). The drawer URL is mirrored in the query string `?event=<id>` so deep-linking works.

### 3.4 New: `NotificationInbox`

Replacement for the current `<ApprovalBell />` dropdown (`components/layout/approval-bell.tsx`). Becomes a full **right-side `Sheet`** (existing shadcn `Sheet`) with the same 3 sections:

1. **Needs your attention** (approvals, urgent items) — unmissable, scrollable.
2. **Today** (all events from the last 24 h, paginated).
3. **Earlier** (collapsible).

Each item is a `<NotificationItem />` that reuses `<ActivityItem />` for rendering and routing.

### 3.5 New: `Builder` (operator surface)

```
┌─────────────────────────────────────────────────────────────────┐
│ [Org Switcher] [Search ⌘K] [Notification Inbox] [Avatar]        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   <BuilderOverview>                                             │
│   ┌──────────┬──────────┬──────────┬──────────┐                 │
│   │ Agents   │ Workflows│ Models   │ Providers│  KPI cards      │
│   │ N active │ N run    │ N enabled│ N healthy│  (live numbers) │
│   └──────────┴──────────┴──────────┴──────────┘                 │
│   ┌──────────┬──────────┐                                        │
│   │ Approvals│ Recent   │  (split: approvals queue + recent     │
│   │   queue  │ runs     │   activity feed embedded)              │
│   └──────────┴──────────┘                                        │
│                                                                 │
│   <BuilderResourceLinks>  (grid: Agents, Workflows, MCP, …)    │
│                                                                 │
│   <BuilderUsageSummary>  (table: top agents by cost/calls)      │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

Reuses existing components: `usage` table from current Dashboard, `approvals` from `useApprovals`, the agents/workflows grids but compacted to a "recent + manage all" pattern.

### 3.6 New: `AgentAvatar` + `AgentStatusPill`

**`<AgentAvatar size? persona state>`** — SVG-based, monochrome (per `design-system/MASTER.md` rule). Visual specs in §5.

**`<AgentStatusPill>`** — sticky top widget. Shows the currently active agent (or "Choose an agent" if none). Tap to open `<AgentSelector>` (a `Popover` listing all agents in the org with avatars and one-tap "switch"). Ambient micro-animation: a 4 px dot pulses when state ∈ {`processing`, `waiting_approval`}.

### 3.7 New: `ActivityDetailDrawer`

Single drawer component with a `kind` switch:

```
<ActivityDetailDrawer eventId kind>
  case 'email_received'  → <EmailDetail />        (reuses /customer-intelligence?email_id=… client)
  case 'approval'        → <ApprovalDetail />     (lifts existing approval form)
  case 'workflow_run'    → <WorkflowRunDetail />  (existing debug-style table)
  case 'agent_release'   → <AgentReleaseDetail /> (existing release comparison)
  case 'integration'     → <IntegrationDetail />
  default                → <GenericEventDetail />
```

URL pattern: `?drawer=email&ref=<id>`. Closing the drawer removes the param. Browser back/forward works. Multiple drawers cannot stack — opening a new one replaces the current.

---

## 4. Data Flow

### 4.1 New backend endpoint: `GET /api/activity/feed`

```
Request:
  ?cursor=<opaque>&limit=50&kinds=email,calendar,workflow_run,approval,agent_run,integration
  Authorization: Bearer <jwt>

Response:
  {
    items: [
      {
        id: string,            // ULID
        kind: "email_received" | ...,
        occurred_at: ISO8601,
        org_id, user_id,
        title: string,         // 1-line, used in notifications
        summary?: string,      // ≤ 280 chars, used in feed cards
        icon: string,          // lucide icon name
        severity: "info" | "warning" | "urgent",
        actor?: { kind: "agent" | "user" | "system", id?, name? },
        subject_id: string,    // FK into the source table
        payload: object,       // kind-specific extras
        read_at?: ISO8601
      }
    ],
    next_cursor?: string,
    unread_counts: { email_received: 3, approval: 1, ... }
  }

Errors: 401 (no auth), 403 (cross-org), 400 (bad cursor).
```

**Backend implementation:**
- New module `backend/app/core/activity/__init__.py` + `feed.py` with `build_feed_for_user(org_id, user_id, filters, cursor)`.
- Aggregator pulls from existing tables via SQL UNION (one round trip):
  - `CustomerIntelligenceNotification` (already exists; maps to `email_*` kinds).
  - `ApprovalRequest` (already exists; maps to `approval_required`).
  - `WorkflowRun` (already exists; maps to `workflow_run_*`).
  - `AgentRun` / `Task` (already exists; maps to `agent_run_*`).
  - `OutboxEvent` (already exists; the project's existing outbox — add a small producer hook on email/calendar event so they appear).
  - Calendar / meeting events are added via `customer_intelligence` notifications or a new thin table; spec keeps it simple: initially events come from the CI service and any other domain that opts in by inserting an `OutboxEvent`.
- A new `MarkActivityRead` endpoint: `POST /api/activity/mark-read` with `{ids: […]}`.
- Cursor: opaque ULID-encoded `occurred_at + id` for stable pagination.

**Caching:** `Cache-Control: private, max-age=10` on the feed; ETag = cursor+limit+kinds. SSE stream (4.2) invalidates TanStack Query on receipt.

### 4.2 New backend endpoint: `GET /api/events/stream` (SSE)

Reuses the existing SSE pattern from `backend/app/api/v1/routes/chat.py:163` (`StreamingResponse` with `X-Accel-Buffering: no`).

```
Request:
  Authorization: Bearer <jwt>  (or cookie; same auth as chat)
  Accept: text/event-stream

Response (chunked text/event-stream):
  event: activity
  id: <ulid>
  data: { kind, occurred_at, subject_id, ... }
  \n\n

  event: heartbeat
  data: { ts }

  // every 25 s while idle
```

**Backend implementation:**
- New module `backend/app/core/activity/events.py` with an in-process `asyncio.Queue` per `org_id + user_id`.
- `OutboxEvent` consumer (background task started in the FastAPI `lifespan` context — currently lives in the main app factory; the exact file is `backend/app/main.py` or whichever module calls `FastAPI(lifespan=…)` today; implementation plan will pinpoint it). Polls `outbox_events WHERE org_id = ? AND user_id IN (org members) AND created_at > last_seen` every 1 s, fans out to matching user queues.
- Each `/api/events/stream` connection reads from its user's queue and yields SSE frames.
- Backpressure: if a client falls behind by > 500 events, drop oldest and emit a `resync` event with the latest cursor so the client can refetch via `GET /api/activity/feed`.

**Why not WebSocket:** Project already chose SSE for chat streaming. Sticking with one transport is operationally cheaper; bidirectional presence/typing is not in scope for v1.

### 4.3 Frontend wiring

- New hook `useEventStream(url, { onEvent })` in `frontend/lib/events/use-event-stream.ts` — wraps `EventSource` with reconnect (exponential backoff capped at 30 s), heart-beat watchdog (reconnect if no message for 60 s), and TanStack Query `queryClient.setQueryData(['activity-feed'], …)` invalidation on receipt.
- `useActivityFeed(filters)` — `useInfiniteQuery` over `/api/activity/feed`; subscribes to the stream; on each `activity` event invalidates the first page; new items prepend optimistically.
- `useMarkActivityRead()` — `useMutation` hitting `POST /api/activity/mark-read`; updates local read state.

### 4.4 Agent state machine (frontend)

Active agent is held in the existing `useChatStore` (`frontend/stores/index.ts:62`) which already persists `agentId` and `sessionId`. We extend it:

```ts
type AgentUiState = "idle" | "listening" | "processing" | "thinking" | "waiting_approval" | "error";
// stored in a NEW store: useAgentPresenceStore (per active agent)
```

State transitions are driven by **chat SSE events** (already produced by `chat.py:163`):
- `chat_run_start` → `processing`
- `agent_message_start` (text token) → `thinking`
- `tool_call` (auto-approved) → `processing`
- `approval_required` → `waiting_approval`
- `chat_run_end` / `chat_run_error` → `idle` / `error`

Idle state has a low-cost ambient animation (a 6 s breathing pulse); `prefers-reduced-motion: reduce` neutralizes it.

---

## 5. Agent Persona System

### 5.1 Per-agent persona model (decision: each agent 1 persona)

Each `Agent` row gets a new persona field on the model and a UI form for it. Default personas ship pre-defined; admins can edit.

**Schema additions (backend `models/agent.py`):**
```python
persona_key: Mapped[str] = mapped_column(String(64), default="atlas", nullable=False)
# Optional human-readable label override; if null, the persona_key's display
# name is used. NOT a free-form hex — we deliberately do not allow custom
# colors so the design-system monochrome rule stays intact (see 9.1.3).
persona_label: Mapped[str | None] = mapped_column(String(64), nullable=True)
persona_greeting: Mapped[str | None] = mapped_column(String(256), nullable=True)
```

**Default persona library (shipped in `frontend/lib/personas/`):**

| Key | Display name | Vibe | Avatar shape | State animations |
|---|---|---|---|---|
| `atlas` | Atlas | Calm, all-rounder | Soft hexagon | gentle 6 s breathing |
| `scout` | Scout | Curious, research-y | Sharp diamond | antenna wiggle every 12 s |
| `forge` | Forge | Builder, dev | Hammer-pad | sparks when processing |
| `sentinel` | Sentinel | Watcher, ops | Shield | scanning sweep when idle |
| `conduit` | Conduit | Communicator | Two rings | pulsing rings when processing |

All avatars are **monochrome SVGs** (per design system rule — no purple, no neon). They are built as React components that take `{ state, size }` props. The shapes are pure geometry; no emoji.

**Visual style:**
- All personas use the existing monochrome palette (`--primary` etc.). A subtle desaturated accent (1 hue per persona, used only for the 1-px ring around the avatar) is allowed within the existing design system constraint of "status colors desaturated to grayscale." The accent is a single tiny badge (12 px corner), not a fill.
- Animations are CSS-driven (`framer-motion` is already in the bundle; reuse it for spring physics on state transitions, e.g. scale 1 → 1.04 → 1 when entering `processing`).
- `prefers-reduced-motion: reduce` → static, no breathing, no sweep.

### 5.2 Where persona shows up

| Location | Size | Behavior |
|---|---|---|
| Top-right `<AgentStatusPill />` | 32 px | Always visible, ambient state. |
| Center composer (when an agent is selected) | 56 px | Larger, full state animations. |
| Activity feed items (when `actor.kind == "agent"`) | 24 px | Inline icon. |
| Approval drawer "Requested by" | 24 px | Inline. |
| Sidebar "Chat" group (next to active agent name) | 20 px | Compact. |
| Agent card (builder list) | 32 px | Static, no animation. |

### 5.3 Persona selection (admin)

On `/builder/agents/[id]/edit`, a new "Persona" section: dropdown of the 5 defaults + "Custom" (upload a 256×256 SVG). Custom SVGs are validated at upload time:
- Must be SVG (no PNG/JPG).
- Color count ≤ 2 (enforced by parsing `<svg>` children).
- File size ≤ 32 KB.
- ViewBox must be 0 0 256 256.

A custom persona is stored as raw SVG in object storage (existing pattern) and served at `/api/agents/[id]/persona-avatar.svg` with `Cache-Control: public, max-age=86400`.

---

## 6. RBAC-aware UI

### 6.1 Permission gates (existing system, reused)

`hasUiPermission(permissions, key)` already exists in `components/layout/app-sidebar.tsx:7`. We add a server-side `get_landing_route(role, permissions)` helper in `lib/auth.ts` and call it from `app/page.tsx` to redirect:

```ts
// app/page.tsx (new)
export default async function RootPage() {
  const role = getCurrentRole();
  if (role === "platform_admin") redirect("/builder/orgs");
  if (role === "org_admin") redirect("/builder");
  redirect("/home");
}
```

> Role names in this spec follow the current backend enum in `backend/app/api/v1/routes/auth.py` (the OIDC callback uses `Role.platform_admin`, `Role.org_admin`, plus `member` / `developer` / `viewer` for the remaining tiers). The legacy `"admin"` string seen in `frontend/app/page.tsx:22` is an old `getCurrentRole()` UI-side alias and is being retired as part of this spec.

### 6.2 Surface-level rules

| Surface | member / developer / viewer | org_admin | platform_admin |
|---|---|---|---|
| `/home` | ✅ default | ✅ reachable | ✅ reachable |
| `/builder` | ❌ (redirected to `/home`) | ✅ default | ✅ |
| `/builder/orgs` | ❌ | ❌ | ✅ |
| Activity feed (read) | ✅ own org only | ✅ own org | ✅ all orgs (read-only) |
| Activity feed (mark read) | ✅ own | ✅ own + impersonate | ✅ any |
| Persona editor on agent | ❌ (read-only) | ✅ for own org's agents | ✅ |
| Custom SVG upload | ❌ | ✅ | ✅ |
| `/admin/email-intelligence` | ❌ | ✅ | ✅ |
| Debug surface | read-only | ✅ | ✅ |

### 6.3 Empty states per role

- `member` with **no agents** assigned → "You don't have an agent yet. Ask your org_admin to share one with you." (no "create" CTA).
- `org_admin` with **no agents** → "Set up your first agent — pick a template or start from scratch." (CTA: `/builder/agents/new`).
- `platform_admin` in a new org → same as `org_admin` (since the org_admin role is implied in the platform org; the actual switch happens via Org Switcher).

---

## 7. Migration Plan

### 7.1 Strategy: feature-flagged rollout with parallel routing

The new surfaces live **alongside** existing pages, not replacing them on day one. A feature flag `OPENAGENT_AGENT_HOME_V2` (env var, default `false` in production) toggles the new behavior.

**Phase 0 — Build in shadow (no user impact):**
- Ship `/home`, `/builder`, the new components, the new backend endpoints behind the flag OFF.
- Dark-launch: `OPENAGENT_AGENT_HOME_V2=true` for `platform_admin` only. Smoke-test the new surfaces in production.
- All existing routes still work; `app/page.tsx` keeps current Dashboard behavior when flag is OFF.

**Phase 1 — Internal dogfood:**
- Enable for `org_admin` of one pilot org. Gather feedback on Activity Feed latency and persona legibility.
- Keep old pages reachable via direct URL.

**Phase 2 — Default ON for end-users:**
- Enable for `member`/`developer`/`viewer`. Old pages auto-redirect to the new surface (with a "classic UI" opt-out for 30 days).

**Phase 3 — Sunset old pages (30 days after Phase 2):**
- `/email-intelligence`, `/customer-intelligence`, `/approvals` (top-level), `/run-workflow`, `/files` (top-level) → return 410 Gone with a link to the new surface.
- The route table at the top of `frontend/app` shrinks from 27 entries to ~14.

### 7.2 Backwards-compat window

For the first 30 days after Phase 2:
- `/email-intelligence` → 302 to `/home?drawer=email&ref=<id>` (preserves `?email_id=` query).
- `/customer-intelligence` → 302 to `/home?drawer=research&ref=<id>`.
- `/approvals` → 302 to `/home?drawer=approval&ref=<id>`.
- `/run-workflow` → 302 to `/builder/workflows?action=run&id=<id>`.
- `/files` → 302 to UserNav menu (handled in shell, no URL).

### 7.3 Telemetry & kill switch

Add minimal client-side counters behind the flag:
- `home_page_viewed` (count, by role).
- `activity_event_received` (count, by kind, with `reconnect=true|false`).
- `drawer_opened` (count, by kind).
- `old_route_hit_302` (count, by source path).

A single env var `OPENAGENT_AGENT_HOME_V2_ROLLBACK=true` instantly disables the flag and reverts the redirects.

---

## 8. Out of Scope (deliberate)

These are listed to prevent scope creep in implementation:

- A real `Cmd+K` command palette.
- Voice input (composer has a placeholder; not implemented).
- Multi-agent conversations on Home (one agent active at a time; multi-agent DAGs still happen in `/builder/workflows/[id]/edit`).
- Real calendar source-of-truth beyond what's in `customer_intelligence` notifications. Calendar events from Google Calendar etc. come through CI as notifications; no new OAuth flows.
- Mobile-native install (PWA). Responsive layout works on mobile but is not a separate UX.
- Inbox-style "archive / snooze" controls on the Activity Feed (added in v2 if telemetry shows demand).
- Persona marketplace (sharing personas across orgs).

### 8.1 Implementation phasing (planning note)

This spec is intentionally large. The follow-up `/start-work` writing-plans phase MUST decompose it into **separate plans** that can ship and be reviewed independently. Recommended split:

1. **Plan A — Backend foundation.** `/api/activity/feed`, `/api/events/stream`, `OutboxEvent` consumer, persona schema migration. (Pure backend, no UX impact.)
2. **Plan B — Design-system persona primitives.** `AgentAvatar`, persona SVG library, `AgentStatusPill`, framer-motion state transitions, `prefers-reduced-motion` handling. (Design system only; ships in Storybook or a demo route.)
3. **Plan C — Home + Activity Feed + Drawer.** `/home`, `ActivityFeed`, `ActivityDetailDrawer`, `useEventStream`, Notification Inbox Sheet. Frontend-only if Plan A's contract is mocked; end-to-end once Plan A ships.
4. **Plan D — Builder + role-based redirect.** `/builder`, `app/page.tsx` redirect, RBAC matrix changes.
5. **Plan E — Migration + deprecation.** 302 redirects, feature flag, telemetry, Phase 3 sunset of legacy routes.

Each plan can be merged, reviewed, and rolled back independently. This decomposition is **mandatory**; do not attempt to ship the full spec as a single PR.

---

## 9. Open Questions & Risks

### 9.1 Open questions (need user decision before implementation)

1. **Default persona for legacy agents** — existing agents have no `persona_key`. On migration, do we **default to `atlas`** for all of them, or do we render a "Pick a persona" prompt on first visit? Recommendation: default to `atlas`, prompt is non-blocking (banner at top of Home).
2. **Right rail on small screens** — the 3-column layout collapses on `md-`. Do we (a) hide the right rail entirely, (b) put it behind a tab, or (c) make it horizontally scrollable below the center? Recommendation: (b) — bottom tab on mobile.
3. **Persona colors** — monochrome is a hard rule from `design-system/MASTER.md`. We propose a *single-pixel* desaturated accent on the corner of the avatar. This is a tiny deviation that the design system should ratify before we ship. **Decision pending.**
4. **Activity Feed retention** — how far back? Recommendation: 30 days in DB, 7 days shown by default. Older items load via cursor. Confirm.
5. **`/home` vs `/builder` switcher for org_admin** — do we expose a manual toggle in the topbar so an org_admin who is also a heavy end-user can land on `/home`? Recommendation: yes, a small "View as user" toggle in UserNav.

### 9.2 Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| SSE through load balancer times out idle users | Med | Med | Heartbeat every 25 s; documented in §4.2. |
| `OutboxEvent` backlog during peak | Med | High | Backpressure drop with `resync` event; client refetches feed. |
| Persona SVG upload used to bypass monochrome | Low | Med | Server-side color count check; admin review of uploaded SVGs before they go live. |
| Drawer URL param causes infinite redirect loops with old `/email-intelligence` 302s | Med | High | Migration phases 7.1, 7.2; integration test that follows a redirect from each old URL to the new one. |
| Activity feed latency > 2 s on cold cache | Med | Med | Backend response includes 10 s `Cache-Control`; TanStack Query warm cache + optimistic prepend on SSE. |
| `AppShell` mode prop is wrong SSR vs. client (hydration mismatch) | Med | Med | Server reads role from session and sets `<body data-mode>`; client never recomputes mode. |
| Users on small screens get a worse experience with 3 columns | Med | Med | 3.1 / 9.1.2 mobile collapse decisions. |
| Scope creep into "make every drawer a page" | High | High | Strictly enforce: every detail = drawer; only builder = page. Document the rule in `components/AGENTS.md`. |
| Test coverage of SSE reconnection logic | Med | Med | Add `useEventStream` test that simulates server close and asserts reconnect. |

---

## 10. Verification Plan (post-implementation)

1. **Unit / integration:**
   - `backend/tests/test_activity_feed.py` — pagination, cursor, RBAC scoping, kind filters.
   - `backend/tests/test_event_stream.py` — connect, receive, heartbeat, backpressure, resync.
   - `frontend/lib/events/use-event-stream.test.ts` — reconnect on close, exponential backoff, query invalidation.
2. **E2E (Playwright):**
   - `frontend/e2e/agent-home.spec.ts` — five common journeys (email received → review; approval required → approve; workflow run started → see live; release published → view; quota warning → open quotas).
   - Click-path audit: every common task ≤ 2 page opens for end-user.
3. **Visual / a11y:**
   - axe-core sweep on `/home`, `/builder`, every drawer state.
   - Lighthouse on `/home`: LCP ≤ 1.5 s on cable.
   - `prefers-reduced-motion: reduce` smoke test.
4. **Telemetry review (T+7 days, T+30 days):**
   - Drawer-open rate vs. page-open rate.
   - SSE reconnect frequency.
   - 302-from-old-route rate (should trend to 0 in 30 days).

---

## 11. References (existing codebase anchors)

- Dashboard current shape: `frontend/app/page.tsx:20`
- Sidebar nav groups: `frontend/components/layout/navigation.ts:17`
- Sidebar rendering: `frontend/components/layout/app-sidebar.tsx:60`
- Approval dropdown (becomes Notification Inbox): `frontend/components/layout/approval-bell.tsx:35`
- Activity feed source data: `frontend/app/email-intelligence/page.tsx:81` (uses `useCustomerIntelligenceNotifications`)
- Chat SSE pattern: `backend/app/api/v1/routes/chat.py:163` (StreamingResponse, `X-Accel-Buffering: no`)
- Existing outbox: `backend/app/models/__init__.py` (OutboxEvent referenced in codegraph)
- Existing approvals: `backend/app/api/v1/routes/approvals.py`
- Auth role detection: `backend/app/api/v1/routes/auth.py` (OIDC callback sets membership/role)
- Design system: `frontend/design-system/MASTER.md` (monochrome, Fira Sans/Code, no purple)
- Permission helper: `frontend/components/layout/app-sidebar.tsx:7` (`hasUiPermission`)

---

**End of spec.** Ready for user review. Once approved, the next step is `/start-work` (writing-plans skill) to break this into a phased implementation plan with one task per backend endpoint, hook, component, and migration phase.

---

## 12. v2 Constraints (supersedes earlier aesthetics)

**Added 2026-08-25 after Stitch render review.** User direction (verbatim):
> "chú ý phải redesign theo base UI hiện tại, càng ít page càng tốt, dễ nhìn, dễ quản lý, thao tác và view. Trông hiện đại và tự nhiên để nhìn vào trông không giống tạo bởi AI"

**These constraints override any aesthetic choice above that conflicts with them.** When in doubt: real codebase > Stitch render > spec v1.

### 12.1 Routes — net reduction 22 → 14

| Removed (becomes 302 then 410) | Replacement |
|---|---|
| `/email-intelligence` | Home Activity Feed filter + email detail Drawer |
| `/customer-intelligence` | Home Activity Feed filter + research Drawer |
| `/approvals` | Notification Inbox Sheet on Home |
| `/run-workflow` | inline action on `/workflows` |
| `/files`, `/workspace` | UserNav dropdown (workspace merged with files) |
| `/automations` | `/builder/automations` |
| `/mcp` | `/builder/mcp` |
| `/models` | `/builder/models` |
| `/providers` | `/builder/providers` |
| `/organizations` | `/builder/orgs` |

**Final structure (14 top-level):**
- Public: `/login`, `/register`, `/oauth/[provider]`
- App: `/` (redirector), `/home`, `/chat`
- Builder: `/builder`, `/builder/agents`, `/builder/workflows`, `/builder/automations`, `/builder/mcp`, `/builder/models`, `/builder/providers`, `/builder/integrations`, `/builder/orgs`
- Admin/operator: `/debug`, `/evaluations`, `/admin/email-intelligence`
- Settings: `/settings/quotas`, `/settings/members`, `/settings/api-keys`

(The exact set will be finalized in the implementation plan; v2 target is "as few as possible".)

### 12.2 Right rail (Quick Glance) on Home — REDUCED to 1 widget

Stitch render had 3 widgets: System Health + Agent Stats + Integrations. v2 rejects this — too dense, looks AI-fabricated.

**v2: single "Today" widget, 2x2 grid of 4 stats:**
- Emails (count + "X flagged" sub)
- Approvals (count + "pending" sub)
- Workflows (count + "done today" sub)
- Quota (% + "used" sub)

Each stat is tappable → opens the corresponding drawer. No System Health, no Agent Stats, no Integrations on Home (those are operator surface on `/builder`).

### 12.3 Activity Feed copy style

Rejects Stitch's dev-tool jargon ("Agent Deployed", "API Key Generated", "Build Success"). Keeps spec v1's user-facing copy style: "Sarah Chen flagged an email for review", "Approval pending: send calendar invite", "Workflow done: Daily research". One title line, one detail line, optional chip. Real customers from the org's data, not fabricated names.

### 12.4 No fictional metrics

Rejects Stitch's "99.9% uptime / 42ms latency / 2.4GB memory" sample data. If a widget shows numbers, those come from a real API call. Empty state shows `--` or `0`, not sample data.

### 12.5 Branding

Rejects Stitch's "Developer Console" sub-title. Keeps codebase's "OpenAgent" + "Agent Platform" sub-title (matches `app-sidebar.tsx:51`).

### 12.6 Backgrounds

Rejects Stitch's pure `#000000`. Keeps codebase's `#0a0a0a` (hsl 0 0% 4%) — softer, less harsh on OLED.

### 12.7 Active nav state

Rejects Stitch's `bg-white/10` + `font-bold`. Keeps codebase's `bg-sidebar-accent` + `font-medium` (subtle). Loud active states look AI-cliché.

### 12.8 Anti-AI-cliché checklist (apply to every screen, every PR)

Before merging any visual change, run this checklist:

1. **No gradient text** on hero (codebase rule)
2. **No purple/neon** anywhere (codebase rule)
3. **No "Powered by AI" / "Intelligent Assistant" / "✨" / "🚀"** in copy
4. **No centered hero** on internal tools
5. **No fake round numbers** (99.9%, 50%, 98.2%) — show `--` or real API value
6. **No 3-column-equal grid** for feature rows
7. **No filler text** ("Scroll to explore", "Get started in 30 seconds")
8. **Real data shapes** — not "Acme Co / Stripe Partners / Lumen Health" unless the org actually has those customers
9. **Vietnamese copy** where the codebase uses Vietnamese; English where codebase uses English (don't switch languages unilaterally)
10. **Match existing voice** — codebase already has its own greeting ("Đội ngũ agent của bạn đang sẵn sàng" on current Dashboard); don't replace with English marketing copy

A PR that fails any of these checks gets rejected with reference to this section.

### 12.9 Implementation phasing reaffirmed

v2 keeps the 5-plan decomposition from §8.1:
1. **Plan A — Backend foundation** (no UX impact)
2. **Plan B — Design system persona primitives** (design system only)
3. **Plan C — Home + Activity Feed + Drawer** (frontend, v2 spec)
4. **Plan D — Builder + role-based redirect** (operator surface)
5. **Plan E — Migration + deprecation** (302 → 410 over 30 days)

Each plan is reviewable + rollbackable independently. Do not ship as a single PR.

### 12.10 Reference

- Stitch render review: `frontend/_mockups/stitch-screens/REVIEW-NOTES.md` (v2 — supersedes v1)
- Stitch 4 PNG mocks: `frontend/_mockups/stitch-screens/01-home.png` … `04-drawer.png`
- Stitch gallery: `frontend/_mockups/stitch-gallery.html`
- HTML mockup v2: `frontend/_mockups/agent-home-v2.html` (Right rail already updated)
- HTML mockup v6 (Final Interactive Simulator): `frontend/_mockups/agent-home-v6.html` (Executive Operator with 3D Stack Carousel, Thought Bubble & Capsule Tabs)

---

## 13. Executive Agent Operator Paradigm (v6 Final Design Reference)

**Finalized 2026-08-25 after user interactive review on `agent-home-v6.html`.**

### 13.1 Core Product Shift: From Passive Chat / Manual DAG to Executive Chief of Staff
1. **Background Routines Are the Core Engine**: The system operates 7 automated routines in the background (`open-agent-worker-1`):
   - **Event-Driven (Group 1)**: `gmail_monitor_and_triage` (`Monitor and triage new Gmail`), `new-customer-intelligence` (`New Customer Intelligence`).
   - **Daily Scheduled Cron (Group 2)**: `morning-command-center` (07:30 daily), `follow-up-radar` (07:30 daily), `meeting-preparation` (07:30 daily), `end-of-day-client-digest` (07:30 daily), `weekly-account-review` (07:30 daily).
2. **The 3D Companion Is an Operator, Not a Form**:
   - The user does not manually trigger DAGs daily.
   - The 3D Robot acts as a personal operator surfacing time-aware briefings, synthesizing customer dossiers, and gatekeeping high-risk actions.

### 13.2 Visual & Interaction Architecture (Living Cybernetic AI)
- **Draggable 3D Companion with Magnetic Docking**:
  - Freely draggable across the viewport.
  - 3 Magnetic Snapping Zones: Center (`#dockCenter`), Bottom-Right (`#dockBottomRight`), Left-Rail (`#dockLeftRail`).
  - Head look-at loop tracking pointer motion smoothly via spring interpolation.
- **Living Thought Bubble (`#thoughtBubble`)**:
  - Frosted glass capsule floating dynamically above the robot's head (`top: -34px`).
  - Displays high-priority real-time alerts (e.g. `✨ 3 hành động cần bạn phê duyệt (Acme Corp, Northstar...) →`).
  - Clicking the bubble or robot smoothly triggers the Command Surface.
- **Smart Clamping & Auto-Flip Surface**:
  - Automatically checks bottom viewport clearance and flips upward (`above` mode) when near bottom edges.
  - Clamps horizontally with a 16px safety margin.
  - Dynamic pointer arrow (`--arrow-x`) aligned with the robot's center.

### 13.3 Multi-Item Scalability Architecture
When managing multiple concurrent approvals, notifications, and briefings, the interface scales gracefully:
1. **3D Stacked Carousel (`[◀ 1 / N ▶]`)**:
   - Cycles through pending approvals one at a time without growing popup height.
   - Each card displays **Reasoning Transparency (3 Steps: Extract ➔ Policy ➔ Action)** + **Confidence Score (98%)** + **Time Saved (~25m)**.
   - Includes **`[✨ Duyệt nhanh tất cả N hành động an toàn]`** (Batch 1-Click Approve).
2. **Segmented Capsule Tabs (`tab-capsule-strip`)**:
   - `⚡ Phê duyệt (count)` (Amber badge).
   - `✉ Email Triage (count)` (Cyan badge).
   - `📋 Báo cáo (count)` (Teal badge).
3. **Micro-Expand Accordion Rows (`micro-list`)**:
   - 1-line compact rows that smoothly expand on click for quick triaging.
4. **Deep-Link Escalation**:
   - Direct escalation links to full-screen views (`/approvals`, `/email-intelligence`, `/customer-intelligence`) when reviewing 50+ historical records.

### 13.4 Preserved 17 Authentic Routes (Zero Destructive Refactor)
All 17 existing routes remain fully supported and navigable in the shell:
`/chat`, `/approvals`, `/email-intelligence`, `/customer-intelligence`, `/mcp`, `/models`, `/providers`, `/workflows`, `/integrations`, `/evaluations`, `/settings/quotas`, `/settings/members`, `/debug`, `/organizations`, `/files`, `/workspace`, and `/home`.

### 13.5 Complete Reference Spec & Mockup
- **Technical Specification**: [`docs/executive-agent-operator-spec.md`](../executive-agent-operator-spec.md)
- **Interactive Simulator**: [`frontend/_mockups/agent-home-v6.html`](../../frontend/_mockups/agent-home-v6.html) (Live on port 8787).

