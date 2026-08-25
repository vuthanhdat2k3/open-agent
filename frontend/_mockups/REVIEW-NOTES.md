# Stitch Mockup — Visual Review Notes v2 (REVISED)

**Date:** 2026-08-25
**Revision:** 2 — pivot to "minimal, natural, anti-AI-cliché" per user feedback
**Source:** Stitch project `projects/11966751620674554804` · design system "Monochrome Logic"

---

## Constraint shift (IMPORTANT — supersedes v1)

User direction (verbatim, 2026-08-25):
> "chú ý phải redesign theo base UI hiện tại, càng ít page càng tốt, dễ nhìn, dễ quản lý, thao tác và view. Trông hiện đại và tự nhiên để nhìn vào trông không giống tạo bởi AI"

Translation:
1. **Redesign based on the CURRENT base UI** — don't invent a new IA, simplify what exists
2. **Fewer pages** — aggressively consolidate
3. **Easy to look at, manage, operate, view** — UX clarity over feature density
4. **Modern + natural** — high craft
5. **Must NOT look AI-generated** — anti-AI-cliché is a hard requirement

The v1 review notes adopted 6 must + 5 should from Stitch. **Several of those are rejected by the new constraint.** v2 supersedes v1.

---

## Re-evaluation under new constraints

### What the current UI has (baseline)

| Page | Lines | What it does | Verdict under "fewer pages" |
|---|---|---|---|
| `/` (Dashboard) | 91 | Greeting + agent/workflow counts + 4 stat cards + approvals list + agent grid + usage table | **Heavy first paint, redundant with /agents and /approvals** — top candidate for simplification |
| `/chat` | ? | Full chat experience | Keep — core surface |
| `/agents` | ? | Agent grid + new dialog | Keep — builder surface |
| `/workflows` | ? | Workflow canvas editor | Keep — builder surface |
| `/run-workflow` | ? | One-off workflow runner | **Merge into /workflows?action=run** |
| `/email-intelligence` | 211 | Email inbox with filters, pagination | **Merge into Home as Activity Feed filter** |
| `/customer-intelligence` | 374 | Research cases + schedules | **Merge into Home as Activity Feed filter** |
| `/approvals` | ? | Approval list | **Replace with right Sheet (already planned)** |
| `/automations` | 928 | Workflow catalog + active list | **Move to /builder/automations** |
| `/integrations` | ? | OAuth connection management | Keep at /builder/integrations |
| `/files` | ? | Uploaded files | **Move to UserNav dropdown** |
| `/workspace` | ? | Workspace artifacts | **Merge with /files into UserNav dropdown** |
| `/debug` | ? | Session inspector | Keep — operator surface |
| `/evaluations` | ? | Eval runs | Keep — operator surface |
| `/admin/email-intelligence` | ? | Admin Email Ops | Keep — admin-only |
| `/settings/*` | ? | Quotas, members, API keys | Keep |
| `/mcp` | ? | MCP servers | Move to /builder/mcp |
| `/models` | ? | Model directory | Move to /builder/models |
| `/providers` | ? | Provider list | Move to /builder/providers |
| `/organizations` | ? | Platform admin org list | Keep at /builder/orgs |
| `/login`, `/register`, `/oauth/*` | ? | Auth | Keep (public) |

**Net reduction: 22 → ~14 routes** by removing `/email-intelligence`, `/customer-intelligence`, `/approvals`, `/run-workflow`, `/files`, `/workspace`, `/automations`, `/mcp`, `/models`, `/providers`, `/organizations` as top-level pages.

---

## What Stitch v1 got right (still keep)

1. **3-column shell on Home is the right call** for end-users — but with **fewer widgets in each column**. Stitch's Quick Glance has 3 widgets (System Health + Agent Stats + Integrations = ~600px of vertical content). That's too much. Keep only 1-2 widgets.
2. **Tool result blocks (terminal output in chat)** — Stitch validated this pattern. Adopt.
3. **Inbox 3-section labels** — "Needs your attention / Today / Earlier" works. Adopt.
4. **Urgent item: red left border + tint background** — cleaner than badge. Adopt.

## What Stitch v1 got wrong (reject under new constraints)

| v1 decision | New verdict | Why |
|---|---|---|
| D5: Activity feed copy "Agent Deployed / API Key Generated / Build Success" | **Reject** — too dev-tool-internal. Use user-facing copy from spec: "Email flagged / Approval pending / Workflow done" | User said "easy to view" — internal jargon fails that |
| D8: Embedded terminal block in agent chat | **Adopt but minimal** — keep for actual tool calls; don't put "command line aesthetic" in everyday chat | Modern + natural means chat feels like chat, not a terminal |
| D9: Quick Glance = System Health + Agent Stats + Integrations | **Reject all 3. Replace with 1 widget: "Today"** (3-4 stats: emails / approvals / workflows / quota) | Less = easier to look at |
| D10: System Health 99.9% / 42ms / 2.4GB | **Reject** — looks like AI-fabricated fake data | Real product, real metrics, no fake "99.9%" |
| D11: 32px activity card icon | **Reject** — 32px is too big for the dense feed | Sticking with 28px (current spec) |
| D17: Background `#000000` (pure black) | **Reject** — pure black screams "designer took the easy route" | Keep `#0a0a0a` from codebase — softer, less harsh |
| Stitch "Developer Console" branding | **Reject** — corporate-speak | Keep "Agent Platform" from codebase — current users know this |
| Stitch active nav: `bg-white/10` + `font-bold` | **Reject** — too loud | Keep current subtle `bg-sidebar-accent` |

---

## New design principles (v2, anti-AI)

### 1. Restraint over completeness
A page that shows **5 things clearly** beats a page that shows **15 things partially**. Cut until it hurts, then cut one more.

### 2. Match the codebase's existing voice
- Vietnamese-friendly copy where the codebase uses it ("Đội ngũ agent của bạn đang sẵn sàng" on current Dashboard is fine, don't replace with English)
- Same lucide icons, same 12px radius, same `shadow-card` elevation
- Don't introduce new design vocabulary — extend what exists

### 3. No fictional metrics
- Don't show "99.9% uptime" or "42ms latency" or "2.4GB memory" as if they're real
- Empty states must look empty, not populated with sample data
- If a widget shows numbers, those numbers come from a real API call

### 4. No decorative "AI tells"
- No "Powered by AI" badges
- No "Your intelligent assistant" taglines
- No "✨" sparkle icons in copy
- No gradient text on hero
- No centered hero on internal tools (the codebase is a B2B dev tool, not a marketing page)

### 5. Progressive disclosure
- Surface 2-3 things per page
- Hide everything else behind explicit clicks
- Drawers over pages, dialogs over drawers, popovers over dialogs

### 6. Same primitives, fewer compositions
- Use the existing 6 component categories from `components/ui/` (Button, Card, Badge, Input, Dialog, Table) — don't invent new atoms
- Use the existing 3 sections from `components/shared/` (EmptyState, ErrorState, LoadingSkeleton, SectionHeader) — don't reinvent

---

## Concrete v2 spec changes (apply these, not v1)

### Home page (end-user)

**Right rail (Quick Glance) — REDUCE from 3 widgets to 1:**
- **Single widget: "Today"** — 4 stats in a 2x2 grid, each a small card with icon + number + label:
  - "Emails" (3 new, 1 flagged)
  - "Approvals" (1 pending)
  - "Workflows" (2 done today)
  - "Quota" (78% used, reset Aug 31)
- Each stat is tappable → opens the corresponding drawer
- **No System Health widget, no Agent Stats widget, no Integrations widget** on Home. Those are operator surface, not user surface.

**Activity Feed (left rail):** keep all 10 event kinds from spec, but copy stays in the **spec's original style** (e.g., "Sarah Chen flagged an email for review"), not Stitch's "Agent Deployed" jargon.

**Center column (chat):** keep spec's design (Atlas pill + thread + composer). Adopt only the **terminal block** for actual tool call results (not as decorative element).

**Composer button:** keep current `Send` text + paper-plane icon (current `ChatComposer` component). Don't change to `arrow_upward`.

### Builder page (operator)

**Top KPIs:** keep 4 cards (Agents / Workflows / Models / Providers). Don't add a 5th.

**Middle split:** keep Approvals + Recent activity. Don't change content.

**Resources grid:** keep 3x2. Don't add a 7th row.

**Usage table:** keep 6 columns. Use **real agent names** the org actually has, not "Atlas / Scout / Conduit / Sentinel / Forge" as if they always exist. The codebase already has agents populated via `/api/agents` — bind to real data.

### Notification Inbox (right Sheet)

**3 sections:** keep "Needs your attention / Today / Earlier". Adopted from spec, validated by Stitch.

**Urgent item style:** red left border (3px) + red tint background (4% destructive). Cleaner than badge.

**Items:** real data from `/api/customer-intelligence/notifications` and `/api/approvals`, not sample data.

### Activity Detail Drawer

**Header:** 40px avatar + subject + sender meta + close X. Stitch validated.

**Sentinel Insights callout:** info-tinted box (6% bg, 20% border, 12px radius). Label "Why [Agent] flagged this" — clearer than spec's "AI summary".

**Body + context + footer:** keep spec layout. 3 buttons: Archive / Ask Atlas / Reply.

### Sidebar

**Width:** 240px (current convention, don't change).
**Brand:** "OpenAgent" + "Agent Platform" (current, don't change).
**Nav order:** keep spec's order (Home first, then Builder, Chat, etc.).
**Active state:** `bg-sidebar-accent` + `font-medium` (current, subtle). Don't adopt Stitch's `bg-white/10` + `font-bold` (too loud).
**Per-role nav:** keep spec's role-based logic (member sees Home/Chat/Approvals; admin sees full builder group).

### Icons

Keep `lucide-react` (codebase-wide, 50+ components already use it). Don't switch to Material Symbols.

### Backgrounds

`#0a0a0a` (current `hsl(0 0% 4%)`). Don't go to pure `#000`.

---

## Out of scope (v2 reaffirms v1's out-of-scope list)

- No Cmd+K command palette
- No voice input
- No multi-agent conversation on Home
- No calendar source-of-truth beyond what CI notifications provide
- No PWA / mobile-native
- No inbox-style archive/snooze
- No persona marketplace

---

## Migration scope (concrete numbers)

| Phase | Action | Routes affected |
|---|---|---|
| Phase 0 | Build `/home` + `/builder` + new components + new backend endpoints behind feature flag (OFF in prod) | New code, 0 deletions |
| Phase 1 | Enable for `org_admin` of pilot org | 0 deletions, monitoring |
| Phase 2 | Enable for end-users. 302 redirects for old routes | 11 routes become 302s |
| Phase 3 | Sunset old routes (410 Gone) | Net **22 → 14 routes** |

**The 8 routes removed by Phase 3:**
- `/email-intelligence` → inbox becomes Home filter
- `/customer-intelligence` → research cases become Home filter
- `/approvals` → Sheet on top of Home
- `/run-workflow` → inline action on /workflows
- `/files` → UserNav dropdown
- `/workspace` → UserNav dropdown
- `/automations` → `/builder/automations`
- `/mcp` → `/builder/mcp`
- `/models` → `/builder/models`
- `/providers` → `/builder/providers`
- `/organizations` → `/builder/orgs`

(That's 11 actually — final count from 22 → 11 top-level + 3 sub-routes under /builder = 14 total.)

---

## Verification — anti-AI-cliché check

Before declaring v2 done, check every screen against:

1. **No gradient text** on hero (codebase rule)
2. **No purple/neon** anywhere (codebase rule)
3. **No "Powered by AI" or "Intelligent Assistant"** taglines
4. **No "✨" or "🚀" emoji** in copy (codebase rule)
5. **No centered hero** on internal tools
6. **No fake round numbers** (99.9%, 50%, 98.2%) in mockup state — show "--" or actual API value
7. **No 3-column-equal grid** for feature rows (use 2-col split or single-col)
8. **No filler text** ("Scroll to explore", "Get started in 30 seconds")
9. **Real data shapes** in every example — not "Acme Co / Stripe Partners / Lumen Health" as if they always exist; the org may have completely different customers
10. **Vietnamese copy** where the codebase uses Vietnamese; English where codebase uses English
