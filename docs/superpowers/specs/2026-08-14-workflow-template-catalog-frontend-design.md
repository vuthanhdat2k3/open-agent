# Workflow Template Catalog — Frontend Design Specification

Date: 2026-08-14
Status: Approved design, ready for implementation planning
Target: Docker Compose/VPS, fewer than 100 users
Primary audience: non-technical, client-facing knowledge workers using Google Workspace
Related system spec: `docs/superpowers/specs/2026-08-14-workflow-template-catalog-design.md`
Related frontend spec: `docs/superpowers/specs/2026-08-13-personal-email-intelligence-frontend-design.md`

## 1. Purpose

This document defines the production frontend for OpenAgent's curated workflow catalog and recurring
automation feature. The experience lets a non-technical user discover useful automations, connect
their own data, choose a safe schedule, enable the automation, and understand its results without
editing a graph or learning scheduler terminology.

The interface must feel like an intelligent work assistant, not an infrastructure console. It must
always make four things clear:

1. what the automation reads;
2. when it runs;
3. what result it produces;
4. which external actions still require approval.

The design uses the existing Next.js, React, Tailwind, shadcn/Radix, Lucide, TanStack Query, and
OpenAgent shell. It does not introduce another component library, animation runtime, or client-side
business-state store.

## 2. Product decisions

### 2.1 Chosen interaction model

The chosen model is a single guided **Automation Hub** with three views:

- Discover;
- Active;
- Activity.

The sidebar contains one user-facing `Automations` destination. Catalog, schedule, installation, and
run history do not become separate navigation groups. Template details and installation settings
open in contextual drawers; setup uses a three-step guided drawer.

### 2.2 User language

The User Workspace does not expose these internal terms:

- node;
- graph;
- occurrence;
- outbox;
- lease;
- dead-letter;
- queue payload;
- cron expression.

User-facing equivalents are `step`, `automation`, `run`, `activity`, `needs attention`, and human
schedule phrases. Internal terms remain available in Admin Operations and advanced diagnostics.

### 2.3 Progressive disclosure

The default surface contains only the decisions necessary to enable an automation. Candidate limits,
provider details, detailed budgets, trusted-policy diagnostics, and technical execution data are
grouped under `Advanced settings` or `Diagnostics`.

Progressive disclosure must not hide permissions, external side effects, approval behavior, cost
limits, or destructive consequences.

## 3. Existing frontend constraints

The implementation reuses:

- Next.js 15 App Router and React 19;
- Tailwind CSS and existing semantic color tokens;
- existing shadcn/Radix components and the shared application shell;
- Lucide React icons already installed in the repository;
- TanStack Query for canonical REST state;
- Zod for response and form validation;
- Sonner for transient confirmation;
- existing server-time, idempotency, capability, and reason-code utilities;
- SSE as an invalidation signal, with REST remaining canonical.

### 3.1 Design-system consistency correction

`frontend/design-system/MASTER.md` describes Fira Sans/Fira Code, while the runtime CSS currently
uses Inter/JetBrains Mono. This specification selects the already-running **Inter + JetBrains Mono**
pair to avoid a font migration, loading cost, and cross-page visual regression. Before implementing
the new pages, update the typography paragraph in `MASTER.md` so the documented source of truth and
runtime tokens agree.

No workflow component may introduce hard-coded colors, radii, shadows, or font families.

## 4. Experience principles

1. **Outcome before mechanism.** Lead with what the user receives, not how the graph runs.
2. **One primary action.** Each card, drawer, and wizard step has one visually dominant action.
3. **Safe by inspection.** Data access, schedule, side effects, approval, and budget are visible
   before enablement.
4. **Canonical truth.** Mutations do not claim success before the server confirms canonical state.
5. **Quiet intelligence.** Recommendations are useful but never visually louder than urgent work.
6. **Compact, not cramped.** Use moderate dashboard density with clear section boundaries.
7. **Explain exceptions.** A blocked or skipped run says why and what the user can do next.
8. **No card soup.** Use rows, sections, separators, and drawers instead of nesting cards repeatedly.
9. **Accessible by default.** Keyboard, screen reader, contrast, reduced motion, and touch sizing are
   release requirements.
10. **Fast on ordinary hardware.** Reserve layout space, paginate history, and avoid animation work on
    long lists.

## 5. Information architecture

### 5.1 User route

```text
/automations?view=discover
/automations?view=active
/automations?view=activity
```

Optional deep-link query parameters:

```text
template=<template-key>
installation=<installation-id>
run=<workflow-run-id>
setup=<template-key>
```

The URL must preserve the selected view, filters, and opened canonical resource so browser Back,
Forward, refresh, and shared authorized links behave predictably.

### 5.2 Sidebar

Add one user-facing navigation item:

```text
Automations — Lucide Zap
```

It belongs in the user productivity section near Smart Inbox, Research Cases, and Integrations.
Existing admin `/workflows` remains the graph-authoring destination and uses the existing Workflow
icon. The two routes must not share a label or icon.

The Automations item shows one badge when the corresponding count is greater than zero, derived from
the server navigation summary:

- ordinary count for new useful results;
- destructive/urgent treatment only for action-required items.

### 5.3 Header and global actions

The standard application header remains sticky. It contains:

- sidebar trigger;
- current page title;
- global notification bell;
- theme control;
- existing user menu.

The Automation Hub page header contains title, one-sentence description, and at most one primary
action: `Browse workflows` when the current view is Active or Activity. It does not contain a large
marketing hero.

## 6. Page anatomy

```text
PageHeader
AutomationStatusStrip
AutomationViewTabs
ViewToolbar
ViewContent
ContextualDrawer or SetupDrawer
```

The page uses the existing centered `max-w-7xl` shell. Desktop content has a 12-column grid, but each
view uses the smallest layout needed:

- Discover: responsive card grid;
- Active: full-width compact rows;
- Activity: full-width timeline/list;
- drawers: contextual details without route loss.

### 6.1 Status strip

The strip is a compact summary, not a row of large metric cards. It contains up to three items:

- active automation count;
- nearest next run;
- action-required count.

Each item is a link to an appropriate filtered view. When all values are zero, show one sentence and
one recommended next action rather than three zero metrics.

## 7. Visual language

### 7.1 Direction

The visual direction is **calm intelligence**: precise monochrome surfaces, clear information
hierarchy, restrained elevation, and tactile but quiet feedback. It inherits the existing OpenAgent
identity rather than applying the generic purple/pink visual language common to AI products.

### 7.2 Color

- Use only semantic tokens from the existing design system.
- Primary interface remains black/white/neutral gray in both themes.
- Destructive red is reserved for destructive actions, failed state, security risk, and breached
  urgency.
- Do not add a workflow-specific brand color.
- Do not use color alone to encode run or installation state.
- Status treatments combine text, icon, and semantic badge variant.

### 7.3 Typography

- UI and report text: Inter.
- IDs, timestamps requiring exact alignment, cost figures, and technical diagnostics: JetBrains Mono.
- Default body size: 16px with at least 1.5 line-height.
- Secondary metadata may use 13–14px; essential body text must not fall below 14px.
- Headings use sentence case, not all caps.
- Workflow names truncate to two lines in cards and one line in compact rows, with an accessible full
  name tooltip only when truncation occurs.

### 7.4 Spacing and density

Use the existing spacing tokens with a working rhythm of `8 / 12 / 16 / 24 / 32px`.

- Card padding: 16–20px.
- Compact row minimum height: 68px desktop, 76px touch layouts.
- Section gap: 24px.
- Major page gap: 32px.
- Interactive controls: minimum 44×44px target.

### 7.5 Surfaces and depth

- Cards use one border, one surface, and restrained `shadow-card`/`shadow-3d-card` tokens.
- Hover lift is permitted only for discoverable template cards.
- Active rows do not move on hover; they use border/background emphasis to avoid list jitter.
- Drawers and dialogs use the existing floating elevation token.
- Do not nest a Card inside another Card for ordinary field groups.
- Avoid permanent blur on every surface; reserve glass treatment for the shell and floating panels.

### 7.6 Motion

- Hover/press feedback: 150–200ms.
- Drawer/dialog transition: 180–240ms.
- State transition: 150–240ms using opacity/transform.
- A catalog entrance may stagger the first six visible cards only.
- Long or virtualized lists do not replay entrance animations.
- No pulsing status dot except a genuinely executing run, and even then it must stop when reduced
  motion is requested.
- `prefers-reduced-motion` disables non-essential movement.

### 7.7 Icons

Use Lucide only. Do not install Phosphor or mix icon styles.

| Meaning | Icon |
|---|---|
| Automations | `Zap` |
| Catalog/Discover | `LibraryBig` |
| Active | `ToggleRight` |
| Activity | `Activity` |
| Next run | `Clock3` |
| Run now | `Play` |
| Pause | `Pause` |
| Resume | `PlayCircle` |
| Schedule | `CalendarClock` |
| Connections | `Plug` |
| Cost/budget | `Gauge` |
| Approval | `ShieldCheck` |
| Notification | `Bell` |
| Needs attention | `TriangleAlert` |
| Success | `CircleCheck` |
| Partial | `CircleDashed` |
| Failure | `CircleX` |

Icon-only controls require an accessible name and tooltip. Do not use emoji as functional icons.

## 8. Discover view

### 8.1 Toolbar

The toolbar contains:

- search by workflow name or outcome;
- compact category filter;
- optional `Works with` integration filter;
- result count announced accessibly.

Search is debounced by 250ms for server queries. Search/filter values live in the URL. Clear filters
uses one visible action when any filter is active.

### 8.2 Recommendation section

Show at most three recommendations above the catalog. Every recommendation includes a short
`Why this fits` explanation generated by deterministic server rules, for example:

> You connected Gmail and Calendar and have meetings this week.

Phase one recommendation ranking does not call an LLM. It considers only authorized metadata such as
connected integration types, already-installed templates, and broad activity counts. It does not
inspect raw email content for merchandising.

If no meaningful recommendation exists, omit the section instead of showing generic recommendations
with false personalization.

### 8.3 Template card

Each card answers the following without opening details:

- What useful result will I receive?
- Which integrations are required?
- What is the default cadence?
- Does it create an external action?
- What is the relative cost tier?

Card anatomy:

```text
[Icon] Workflow name                          [Recommended]
       One-line outcome

Integration chips                     Human schedule
Approval behavior                     Cost tier

                                   View details  Set up
```

Rules:

- The card is not a nested interactive target. Its title and explicit `View details` action open the
  drawer; `Set up` remains an independent button.
- `Set up` is the single primary action.
- Installed templates replace `Set up` with `View automation`.
- Integration chips display service names, not connection IDs.
- Cost uses `Low`, `Medium`, or `High` plus a tooltip/range from canonical metadata.
- Approval text says `No external actions`, `Approval required`, or `Trusted rule eligible`; it never
  says `Fully automatic` when a side effect can still be gated.

### 8.4 Template detail drawer

Desktop width is 560–640px. Mobile uses a full-screen sheet. Sections:

1. outcome and best-for statement;
2. `How it works` as three to five natural-language steps;
3. example result preview;
4. required/optional integrations;
5. default schedule;
6. data access and side effects;
7. cost and limits;
8. primary `Set up automation` action.

The drawer does not render the compiled graph. An admin with diagnostics capability may follow a
link to the managed workflow in the admin builder, but that link is not shown to ordinary users.

## 9. Setup drawer

Setup is one drawer with a visible three-step progress indicator. Desktop preserves the catalog in
the background; mobile uses a full-screen sheet. Closing with unsaved changes requires confirmation.

### 9.1 Step 1 — How it should run

Show:

- workflow outcome preview;
- recommended schedule preselected;
- safe schedule choices supported by the backend;
- timezone label and next three calculated run times;
- workflow-specific plain-language options.

Supported schedule controls:

- every hour;
- every 2, 3, 4, 6, or 12 hours;
- daily at a selected time;
- weekdays at a selected time;
- weekly on one selected day/time;
- event-driven, when the template owns an event trigger.

Do not display or accept raw cron. Default timezone is `Asia/Ho_Chi_Minh` for the current target, but
the control displays the installation's canonical IANA timezone. The preview must account for DST in
other selected timezones and use server-calculated next occurrences.

### 9.2 Step 2 — Data connections

Each integration is a connection row with:

- provider icon and friendly name;
- connected account identity;
- health/status;
- required or optional label;
- short explanation of how the workflow uses it;
- connect, choose, or reconnect action from server capabilities.

Behavior:

- Auto-select the only healthy compatible connection owned by the user.
- If multiple accounts exist, require an explicit choice.
- Never ask the user to enter a connection ID.
- Optional integrations live under `Optional data` and are collapsed initially.
- Missing OAuth scope shows the missing capability in user language before reauthorization.
- Provider tokens and raw scopes are never displayed.

### 9.3 Step 3 — Review and enable

The review is a concise safety contract:

```text
This automation will
• Read new email from <account>
• Check the next 36 hours in <calendar>
• Create a private morning summary at 07:30 on weekdays

This automation will not
• Send email automatically
• Create or change calendar events without approval

Estimated cost
Low — up to $0.08 per run, daily cap $1.00
```

Required elements:

- selected accounts;
- human schedule and timezone;
- data read/write scope;
- approval behavior;
- estimated run and daily budget;
- notification destination;
- link to advanced settings;
- primary `Enable automation` action.

Enabling is not optimistic. Disable the button and show in-button progress during submission. On
canonical success, replace the wizard with a confirmation state containing:

- enabled status;
- next run;
- notification behavior;
- `Run a test now` when capability allows;
- `View automation` action.

### 9.4 Advanced settings

Advanced settings are collapsed by default and grouped by meaning:

- data window and candidate limits;
- run and daily budget;
- notification preferences;
- trusted policy when server policy exposes it;
- missed-run behavior if user-configurable.

Server bounds are shown as helper text. A dangerous or invalid value fails closed and produces an
inline error from a stable reason code. Advanced settings never permit bypassing approval, tenant
scope, provider scope, or the template's hard policy.

## 10. Active view

### 10.1 Toolbar and sorting

Default sort priority:

1. needs attention;
2. running;
3. next run ascending;
4. paused;
5. name.

Toolbar supports search and state filter. The default list is cursor-paginated and does not fetch all
installations when the catalog grows.

### 10.2 Installation row

Desktop row:

```text
[Icon] Morning Command Center       Running
       Next: tomorrow at 07:30      Last: completed in 18s
       Gmail · Calendar             Low cost             [More]
```

Mobile row stacks metadata into two short lines. It preserves a 44px action target.

The `More` menu contains only actions enabled by server capabilities:

- run now;
- edit schedule;
- pause/resume;
- view connections and permissions;
- view cost and limits;
- delete automation.

Missing capability data hides the mutation; the UI does not infer permission from owner or role.

### 10.3 State language

| Canonical state | User label | Primary guidance |
|---|---|---|
| enabled | Running | Show next run |
| paused | Paused | Resume when ready |
| needs_reauthorization | Reconnect required | Open connection recovery |
| degraded | Needs attention | Show actionable reason |
| disabling | Finishing current run | Explain no new runs are accepted |
| disabled | Off | Enable or delete |
| deleted | Removed | Not shown in default list |

An installation switch is not the sole status representation. Pause/resume must show a label and
canonical response. If a run is already claimed, pausing states that the current run may finish.

## 11. Installation detail drawer

The drawer is shared between Active and deep links. It contains:

1. **Overview** — outcome, state, next run, last run, connected accounts.
2. **Latest result** — structured report preview with source links.
3. **Recent activity** — five newest runs and a link to filtered Activity.
4. **Settings** — schedule, connections, budget, notification, advanced policy.

The latest result uses semantic sections rather than one long markdown block. Reports support:

- executive summary;
- priority/action list;
- meetings;
- company/contact information;
- open questions/warnings;
- sources.

Sections with no data show one short missing-data statement; they do not render fabricated filler.
Sources open safely in a new tab with `noopener noreferrer`. Remote email images remain blocked by
default.

## 12. Activity view

### 12.1 List behavior

Activity is cursor-paginated, newest first. It supports filters for:

- automation;
- status;
- date range;
- scheduled/event/manual trigger;
- action required.

The UI does not load node-level traces until the user opens a run. Ordinary users see a concise run
summary; technical diagnostics require a capability.

### 12.2 Activity item

Every run item shows:

- automation name;
- start/end or current duration;
- trigger in human language;
- succeeded, partial, skipped, failed, or running state;
- number of source items considered;
- result/approval link;
- cost and LLM-call summary when available;
- one stable actionable reason when attention is required.

`Skipped` is neutral when caused by no new data or overlap policy; it must not look like a system
failure. `Partial` distinguishes a useful bounded result from success and failure.

### 12.3 Run detail

Run detail opens a drawer and reloads canonical state. Sections:

- summary;
- result artifact;
- source/provenance list;
- approval and external action state;
- cost and duration;
- warnings;
- diagnostics when authorized.

A running detail refreshes through SSE invalidation, with 15-second polling only while the stream is
disconnected and the run remains non-terminal. The stream does not mutate business state directly.

## 13. Recommendations and smart defaults

Phase-one recommendations are deterministic and transparent.

| Signal | Recommendation |
|---|---|
| Healthy Gmail + Calendar | Morning Command Center, Meeting Preparation |
| Repeated customer-message activity | Follow-up Radar, Customer Intelligence |
| Active daily workflows | End-of-day Client Digest |
| Sufficient weekly account activity | Weekly Account Review |
| Missing required connection | Connection CTA before setup |

Rules:

- Already-installed templates are not shown as new recommendations.
- `Why this fits` is returned by the server as a stable reason code plus localized parameters.
- Recommendations use only authorized metadata and aggregate counts.
- The frontend never invents recommendation reasons.
- Lack of a recommendation is a valid state; do not fill space with generic cards.

## 14. Dashboard integration

Add one compact widget titled `What your agents handled today`. It contains at most four linked
facts, for example:

- email screened;
- meetings prepared;
- follow-ups needing attention;
- pending approvals.

The widget is a summary and links to filtered Automation Hub views. It does not duplicate catalog,
settings, or activity controls. If no automation is installed, the widget becomes one recommended
setup CTA. If the user lacks route capability, it is omitted.

## 15. Global notifications

The existing global bell is the persistent notification surface. Workflow notifications include:

- useful result ready;
- approval required;
- approval expiring soon;
- installation needs reauthorization;
- run failed with a user-actionable recovery;
- budget near/at limit;
- system policy changed and disabled an installation.

Notification priority:

| Level | Examples | Treatment |
|---|---|---|
| information | Daily summary ready | Ordinary count |
| attention | Reconnect, partial result | Emphasized row |
| urgent | Approval expiring, repeated failure | Red urgent count and explicit label |

Notifications are signals only. Selecting one deep-links to the resource ID, then the client fetches
canonical REST state. SSE carries only invalidation/resource metadata. Mark-read may be optimistic and
must roll back on failure; approval, retry, reconnect, pause, delete, and run-now are not optimistic.

## 16. Empty, loading, and error states

### 16.1 Empty states

| Context | Message/action |
|---|---|
| No installation | Show one best-fit workflow and Browse workflows |
| Installed, no run yet | Explain next run and offer Run a test now |
| Run found no relevant data | State that no action was needed; do not call it an error |
| No activity for filters | Clear filters |
| Missing connection | Connect/reconnect specific provider |
| No recommendation | Render catalog directly |

### 16.2 Loading

- Show skeletons after 300ms to avoid a flash for fast cached reads.
- Skeleton geometry matches cards/rows and reserves final dimensions.
- A mutation button disables and shows progress immediately.
- Background refresh does not replace populated content with a full skeleton.
- Running status has text plus a subtle progress treatment; no indefinite decorative animation.

### 16.3 Stable error behavior

| HTTP/state | User behavior |
|---|---|
| 400 | Show field/reason-code errors inline |
| 401 | Clear sensitive caches and route to sign-in |
| 403 | Show permission state, refresh navigation capabilities |
| 404 | Close stale drawer, remove stale list item after refetch |
| 409 | “This request was already handled”; reload canonical resource |
| 412 | “This automation changed”; reload and preserve safe form fields only |
| 422 | Show server validation near affected setting |
| 429 | Show retry-after; do not auto-loop mutations |
| 5xx | Preserve context and offer canonical retry |
| timeout/unknown mutation outcome | Show `Verifying outcome`, poll canonical command/resource state |

Error messages use stable reason-code mappings and never display raw provider payloads.

## 17. View-model contracts

The frontend validates responses with Zod. All mutation-capable resources include server-computed
capabilities and blocked reasons.

### 17.1 Envelope

```json
{
  "data": [],
  "meta": {
    "server_time": "2026-08-14T03:00:00Z",
    "next_cursor": null,
    "request_id": "req_123"
  }
}
```

### 17.2 Catalog item

```json
{
  "key": "morning-command-center",
  "version": 1,
  "name": "Morning Command Center",
  "outcome": "Start the day with priorities, meetings, and important email.",
  "category": "daily_planning",
  "icon": "sunrise",
  "required_integrations": ["gmail", "google_calendar"],
  "optional_integrations": ["google_drive"],
  "default_schedule_label": "Weekdays at 07:30",
  "cost_tier": "low",
  "estimated_cost_usd": {"per_run_max": "0.08"},
  "side_effect_policy": "none",
  "installed": false,
  "recommendation": {
    "recommended": true,
    "reason_code": "CONNECTED_GMAIL_AND_CALENDAR",
    "params": {}
  },
  "capabilities": {
    "can_view": true,
    "can_install": true
  },
  "blocked_reasons": {}
}
```

### 17.3 Installation list item

```json
{
  "id": "installation_uuid",
  "template_key": "morning-command-center",
  "name": "Morning Command Center",
  "icon": "sunrise",
  "status": "enabled",
  "status_reason_code": null,
  "next_run_at": "2026-08-15T00:30:00Z",
  "last_run": {
    "id": "run_uuid",
    "status": "succeeded",
    "started_at": "2026-08-14T00:30:00Z",
    "duration_ms": 18000,
    "cost_usd": "0.031"
  },
  "connections": [
    {"provider": "gmail", "display_identity": "u***@example.com", "health": "healthy"}
  ],
  "attention": {"required": false, "reason_code": null},
  "version": 4,
  "capabilities": {
    "can_run_now": true,
    "can_edit_schedule": true,
    "can_pause": true,
    "can_resume": false,
    "can_delete": true,
    "can_view_diagnostics": false
  },
  "blocked_reasons": {}
}
```

### 17.4 Activity item

```json
{
  "run_id": "run_uuid",
  "installation_id": "installation_uuid",
  "automation_name": "Morning Command Center",
  "status": "partial",
  "trigger": {"type": "scheduled", "label": "Weekday schedule"},
  "started_at": "2026-08-14T00:30:00Z",
  "finished_at": "2026-08-14T00:30:20Z",
  "source_item_count": 24,
  "llm_call_count": 2,
  "cost_usd": "0.041",
  "result": {"type": "notification", "id": "notification_uuid"},
  "reason_codes": ["OPTIONAL_DRIVE_UNAVAILABLE"],
  "capabilities": {"can_view": true, "can_retry": false, "can_view_diagnostics": false}
}
```

### 17.5 Navigation summary

Navigation badges use a dedicated unfiltered endpoint, not a filtered list response:

```json
{
  "automations": {
    "new_results": 3,
    "attention_required": 1,
    "urgent": 0
  }
}
```

Filtered response counts describe only the current result set and must not drive global navigation.

## 18. Client data flow

### 18.1 Query keys

All keys include organization scope:

```text
["automation-catalog", orgId, filters]
["automation-template", orgId, templateKey, version]
["automation-installations", orgId, filters]
["automation-installation", orgId, installationId]
["automation-activity", orgId, filters]
["automation-run", orgId, runId]
["navigation-summary", orgId]
["notifications", orgId, filters]
```

Signout and organization switch cancel in-flight requests and remove prior organization queries.

### 18.2 REST and SSE

1. REST loads canonical lists/details.
2. SSE reports a changed resource type and ID.
3. Client invalidates the narrowest matching query.
4. REST reloads canonical state.
5. A missed/reconnected stream invalidates relevant summaries and open details.

The client never reconstructs a run or installation state machine from stream events.

### 18.3 Mutations

Client-generated HTTP `Idempotency-Key` protects API double-submit/network retry. It is independent
of the server-generated provider side-effect idempotency key, which is never exposed to the browser.

State-changing requests include `expected_version` where supported. The UI updates only from the
canonical mutation response or a subsequent refetch.

### 18.4 URL state

Use URL search parameters for view, filters, cursor reset inputs, and opened resource. Ephemeral form
drafts remain local to the drawer. Closing a drawer removes only its resource parameter and preserves
the list/filter state.

## 19. Forms and schedule controls

- Every field has a visible label above the control.
- Placeholder text is an example, never the only label.
- Validation appears near the field and in an announced summary only when submission fails.
- Time selectors use locale-aware display and canonical IANA timezone.
- Show the next three server-calculated runs after schedule changes.
- Disable unavailable schedule types with a visible reason, not a silent disabled control.
- Connection selectors display provider identity and health, not UUIDs.
- Budget input shows server min/max and estimated cadence impact.
- Destructive delete requires a confirmation dialog; require typing the automation name only when the
  installation has material retained history or pending actions.

## 20. Accessibility

Target WCAG 2.2 AA.

### 20.1 Keyboard and focus

- All actions are reachable in visual order.
- Drawers trap focus and restore it to the opening control.
- On open, focus the drawer heading or first explanatory content, not the enable/delete action.
- Setup step changes move focus to the new step heading.
- Escape closes non-destructive drawers; dirty setup asks for confirmation.
- Menus, tabs, segmented controls, and dialogs use established Radix keyboard behavior.
- Skip-to-content remains available in the shell.

### 20.2 Semantics and announcements

- One `h1` per page and sequential heading hierarchy.
- Tabs expose selected state and associated panels.
- Mutation errors use `role=alert` or appropriate `aria-live`.
- Background refresh does not announce repeatedly.
- Countdown and running duration use `aria-live=off`; urgent state changes announce once.
- Icon-only actions have `aria-label` and a visible tooltip.
- Status always includes text, not just icon/color.

### 20.3 Contrast and motion

- Body text contrast is at least 4.5:1.
- Large text and non-text controls meet WCAG requirements.
- Focus ring remains visible in both themes.
- Reduced-motion mode removes stagger, lift, pulse, and non-essential transitions.

## 21. Responsive behavior

### 21.1 Breakpoints

Validate at 375px, 768px, 1024px, and 1440px.

| Surface | Desktop | Tablet | Mobile |
|---|---|---|---|
| Discover | 3 columns | 2 columns | 1 column |
| Active | Compact rows | Compact rows | Stacked rows |
| Activity | Timeline/list | Timeline/list | Activity cards |
| Detail drawer | 560–640px | Near full width | Full-screen sheet |
| Setup drawer | 640px | Near full width | Full-screen sheet |
| Filters | Inline | Mixed | Search + filter sheet |

### 21.2 Mobile specifics

- View tabs become a horizontally safe segmented control with three items.
- Primary setup action remains visible in a bottom action region without covering scroll content.
- Safe-area padding is applied to full-screen sheets.
- No desktop table is squeezed into mobile.
- Long workflow names and account identities wrap/truncate without horizontal page scroll.
- Browser zoom is never disabled.

## 22. Performance

### 22.1 Data and rendering

- Catalog and installation APIs are cursor/filter aware.
- Activity is cursor-paginated newest-first.
- Do not fetch run trace/node detail in list responses.
- Debounce remote search by 250ms and cancel superseded requests.
- Keep previous page data during pagination.
- Virtualize only when a rendered list can exceed 100 complex rows; cursor pagination remains primary.
- Dynamic-import advanced diagnostics and report-heavy renderers.
- Reserve dimensions for skeletons and async badges to keep CLS below 0.1.

### 22.2 Bundle and media

- Reuse Lucide and existing components; no second icon/component/animation library.
- Do not ship template hero illustrations in phase one.
- If illustrations are added later, use optimized AVIF/WebP through Next Image with reserved aspect
  ratio and lazy loading below the fold.
- Avoid blur and shadow combinations that trigger excessive repaint on scrolling lists.

### 22.3 Interaction targets

- Cached tab switch should feel immediate.
- Show progress for operations exceeding 300ms.
- Search/filter interaction should remain responsive with 100 catalog items.
- Activity pagination should not block the main thread with full-history transforms.

## 23. Security and privacy

1. UI visibility is not an authorization boundary.
2. Every action uses server-computed capabilities.
3. Missing capabilities fail closed.
4. The client never supplies owner/org inferred from UI state as authorization proof.
5. Connection IDs are internal values; user-visible controls use masked friendly identities.
6. OAuth tokens, raw scopes, object-store keys, raw provider payloads, and executor keys are never
   rendered or logged in browser telemetry.
7. Email/web/report content is sanitized and treated as untrusted data.
8. Remote email images remain blocked by default.
9. External links use safe target/rel behavior.
10. Side-effect state is never optimistic.
11. Organization switch/signout clears scoped cache and open sensitive drawers.
12. Recommendation reasons do not expose raw personal content.

## 24. Analytics and product metrics

Track bounded product events without raw content:

```text
automation_hub_viewed{view}
automation_template_viewed{template_key}
automation_setup_started{template_key}
automation_setup_step_completed{template_key,step}
automation_setup_abandoned{template_key,step,reason_code}
automation_enabled{template_key}
automation_run_now_requested{template_key}
automation_paused{template_key}
automation_result_opened{template_key,result_type}
automation_recommendation_opened{template_key,reason_code}
```

Do not include email subject/body, account email, report text, URL query content, connection ID, or
provider payload in analytics. Primary success measures:

- setup completion rate;
- time to first useful result;
- active installations per enabled user;
- weekly useful-result open rate;
- pause/disable rate by stable reason;
- reconnect recovery rate;
- approval backlog caused by automations.

## 25. Component boundaries

Suggested focused modules:

```text
frontend/app/automations/page.tsx
frontend/components/automations/
  automation-hub.tsx
  automation-status-strip.tsx
  automation-view-tabs.tsx
  discover-view.tsx
  template-card.tsx
  template-detail-drawer.tsx
  setup-drawer.tsx
  setup-schedule-step.tsx
  setup-connections-step.tsx
  setup-review-step.tsx
  active-view.tsx
  installation-row.tsx
  installation-detail-drawer.tsx
  activity-view.tsx
  activity-item.tsx
  run-detail-drawer.tsx
  schedule-picker.tsx
  connection-row.tsx
  cost-summary.tsx
  automation-status.tsx
  dashboard-automation-summary.tsx
frontend/lib/automations/
  api.ts
  schemas.ts
  query-keys.ts
  reason-registry.ts
  url-state.ts
  schedule-labels.ts
  view-models.ts
```

Large page orchestration stays in `automation-hub.tsx`; cards/rows do not fetch data independently.
Drawers receive IDs and own canonical detail queries. Shared server-time, idempotency, and capability
utilities are reused rather than duplicated.

## 26. Testing strategy

### 26.1 Unit and component tests

- template card state and action hierarchy;
- deterministic recommendation reason rendering;
- installation status mapping;
- capability false/missing hides mutations;
- schedule picker and next-run preview;
- timezone and server-time formatting;
- connection auto-selection rules;
- cost and budget summary;
- activity status and skipped/partial semantics;
- notification priority and badges;
- reason-code localization fallback;
- URL state parse/serialize;
- mutation verification state.

### 26.2 Setup integration tests

- healthy single connection auto-selects;
- multiple connections require selection;
- missing required connection blocks enable;
- optional connection may be skipped;
- missing scope routes to reauthorization;
- invalid schedule/budget shows inline error;
- double-submit uses one client idempotency key;
- 409 and 412 reload canonical state with distinct messages;
- timeout enters verifying outcome and never auto-submits again;
- successful enable displays canonical next run.

### 26.3 Accessibility tests

- keyboard-only catalog, drawer, wizard, menu, and filters;
- focus entry/restore and dirty-close confirmation;
- heading and landmark structure;
- status has text alternative;
- errors are announced;
- touch targets are at least 44×44px;
- reduced-motion behavior;
- automated axe scan on all major states.

### 26.4 Playwright E2E

1. Discover → template detail → setup → enable → canonical confirmation.
2. Run test now → running → result ready → open structured report.
3. Pause while a run is active → current run remains truthful → no next dispatch.
4. Resume → next schedule restored.
5. Reconnect-required state → OAuth recovery → enabled state.
6. Approval notification appears without navigating to Approval Center first.
7. Global bell and Dashboard widget deep-link to canonical resources.
8. Activity filters, cursor pagination, deep link, and browser Back preserve state.
9. Delete confirmation and retained-history behavior.
10. Organization switch/signout clears old-tenant catalog, installation, activity, and notification
    caches.

### 26.5 Responsive and visual regression

Capture light/dark snapshots at 375, 768, 1024, and 1440px for:

- discover empty/recommended/populated;
- setup each step and validation;
- active healthy/paused/attention;
- activity running/partial/failed/empty;
- detail drawer and full-screen mobile sheet;
- global notification states.

## 27. Release gates

The feature cannot leave internal rollout until:

- frontend typecheck, build, unit/component tests, and Playwright E2E pass;
- Lighthouse accessibility score is at least 95 on representative pages;
- no critical axe violation exists;
- CLS is below 0.1 for catalog, Active, Activity, and drawer opening;
- all mutation buttons are capability-gated and non-optimistic;
- timeout/409/412 behavior is verified;
- keyboard and screen-reader review passes;
- light/dark and four responsive breakpoints pass visual review;
- a catalog of 100 templates and paginated activity remain responsive;
- no sensitive content appears in URL, browser logs, analytics, or error UI;
- org-switch/signout cache isolation passes;
- setup abandonment and first-result metrics are observable;
- rollback can hide the route/navigation item without deleting installations or runs.

## 28. Rollout

### FE-1 — Read-only catalog

Expose Discover to internal users with template details, recommendations, and no installation
mutation.

### FE-2 — Guided setup

Enable installation and canonical confirmation for internal users. Keep automatic dispatch disabled or
shadowed at the backend.

### FE-3 — Active and run-now

Enable Active, installation details, safe schedule editing, and test runs for one allowlisted org.

### FE-4 — Activity and notifications

Enable run history, result drawers, Dashboard summary, and global notification deep links.

### FE-5 — P0 controlled rollout

Enable the three P0 templates for selected users, monitor setup abandonment, first-result latency,
error rate, budget, and approval backlog.

### FE-6 — General availability

Release after backend release gates, accessibility/performance gates, backup/restore drill, and
support runbook are complete.

## 29. Final UI invariants

1. One user-facing Automations destination contains Discover, Active, and Activity.
2. A non-technical user can enable a recommended workflow without seeing graph, node, cron, or IDs.
3. Before enablement, the UI states data access, schedule, output, side effects, approval, and cost.
4. Every mutation is capability-gated and revalidated by the server.
5. Side-effect and lifecycle mutations are never optimistic.
6. SSE invalidates; REST supplies canonical state.
7. Schedule previews use canonical timezone and server-calculated occurrences.
8. The newest activity appears first and history is cursor-paginated.
9. Recommendations are deterministic, explainable, and do not inspect raw content for merchandising.
10. Status is never encoded by color alone.
11. Mobile keeps all primary actions reachable with at least 44×44px targets.
12. User Workspace avoids infrastructure terminology.
13. No workflow page introduces a second component, icon, animation, or color system.
14. Organization switch/signout cannot leave prior-tenant data visible.
15. Empty and skipped work are truthful outcomes, not fabricated reports or false failures.
