# OpenAgent Frontend shadcn/ui Refactor Design

**Date:** 2026-08-07  
**Status:** Design approved by user; implementation pending spec review  
**Scope:** Frontend UI refactor only. Business logic, API contracts, routing, permissions, and backend behavior are out of scope.

## 1. Design read and goals

OpenAgent is a technical B2B developer-tool platform for multi-agent workflows. The UI should feel precise, calm, and operational rather than decorative: dark-first surfaces, one restrained emerald accent, readable technical typography, clear hierarchy, and predictable interaction states.

The refactor goal is to replace inconsistent hand-built UI with a maintainable shadcn/ui foundation while preserving behavior. shadcn/ui components and compatible AI/chat patterns are the default implementation primitives. Custom components remain appropriate for product-specific behavior such as workflow canvas, streaming chat rendering, approval interactions, organization switching, and domain-specific tables/forms; those components must compose shadcn primitives rather than recreate them.

Success means:

- Every primary route uses the shared design language and appropriate shadcn components.
- No custom primitive duplicates a shadcn equivalent.
- API calls, route URLs, auth, permissions, validation, CRUD, streaming, uploads, approvals, and state management continue to work unchanged.
- Pages are responsive at 360/390/768/1280/1440px and usable with keyboard and screen readers.
- Each relevant route has explicit loading, empty, error, disabled, and mutation feedback states.
- Typecheck, lint, tests available in the repository, and production build pass.

## 2. Current project audit

### Stack and configuration

- Next.js 15 App Router, React 19, TypeScript strict mode.
- Tailwind CSS 3.4 with CSS-variable-driven shadcn configuration.
- TanStack Query for server state, Zustand for chat/workflow state, React Hook Form + Zod in part of the form layer, Sonner for feedback, Lucide for icons.
- `components.json` already targets shadcn `new-york`, RSC, CSS variables, and aliases `@/components` / `@/components/ui`.
- Existing semantic tokens are present in `app/globals.css`; dark is default and emerald is the primary accent.
- Existing design source of truth: `frontend/design-system/MASTER.md`.

### Existing UI foundation

`components/ui` currently contains partial implementations of Button, Input/Label/Textarea, Select, Dialog, Card, Badge, Skeleton, and Table. Radix dependencies already cover dialog, dropdown menu, select, slot, tabs, toast, and tooltip. Other primitives will be added only after a page inventory proves they are needed. Dependencies must be checked and pinned before installation; no blanket component installation.

### Main structural issues

- The app shell, navigation data, auth gate, prefetch behavior, desktop sidebar, mobile drawer, header, and theme controls are concentrated in `app/layout.tsx` rather than separated into focused layout components.
- The mobile drawer is a hand-built dialog-like overlay and should become a shadcn Sheet or equivalent compatible primitive while preserving open/close behavior.
- Several forms manually manage labels, errors, and submission states instead of consistently using shadcn Form composition.
- Multiple destructive actions use `window.confirm` and should become AlertDialog flows with the same mutation callbacks.
- Empty/loading states are inconsistent; some routes have skeletons while error and retry states are missing.
- Listing pages use a mixture of cards, tables, and ad-hoc action rows without a shared page/list pattern.
- The current chat and workflow pages contain substantial streaming, SSE, canvas, drag/drop, and recovery logic. They must be treated as feature surfaces, not rewritten as generic UI.
- The existing CSS contains visual effects such as gradients, ambient blooms, and 3D shadows. These will be calibrated and tokenized rather than indiscriminately removed.

## 3. Route and UI inventory

| Area | Route(s) | Current pattern / behavior | Refactor direction | Priority |
|---|---|---|---|---|
| App shell | All private routes | Layout, auth gate, sidebar, mobile overlay, prefetch, org/user controls live in root layout | Extract AppShell, AppSidebar, AppHeader, MobileNav; use Sidebar/Sheet-compatible shadcn primitives | P0 |
| Global states | `loading.tsx`, `error.tsx` | Basic skeleton and retry card | Shared LoadingSkeleton and ErrorState with semantic Alert, retry action, focus behavior | P0 |
| Dashboard | `/` | Hero, agent launch cards, stats, usage table | First complete vertical slice with PageHeader/SectionHeader, Card, Table, Skeleton, EmptyState, Alert/error state | P1 |
| Chat | `/chat` | SSE streaming, session recovery, approvals, typewriter buffer, message renderer | Preserve logic; refactor shell/composer/thread/status controls with ScrollArea, Textarea, Button, Badge, Alert and compatible AI/chat patterns | P2 |
| Agents | `/agents`, `/agents/[id]/a2a` | Card grid, create/edit dialog, tool search, risk tiers, releases | Form, Dialog, Command/Combobox only when required, Checkbox/Switch, Badge, AlertDialog; keep AgentCard and release domain logic | P1/P2 |
| Workflows | `/workflows` | Graph canvas, drag nodes, edge creation, SSE run stream, logs | Preserve custom canvas and store; use shadcn Toolbar-like composition, Dialog, Select, Input, Tabs, ScrollArea, Alert, Button | P2 |
| Infrastructure | `/providers`, `/models`, `/mcp` | Card grids, CRUD dialogs, connect/test/delete actions | Shared resource card/list pattern; Dialog, Form, Select, Badge, Skeleton, EmptyState, AlertDialog, DropdownMenu as needed | P1 |
| Workspace | `/workspace`, `/files` | Artifact/execution surfaces and upload/ingest table | Table, Card, Progress where needed, Input, DropdownMenu, AlertDialog, Skeleton, empty/error/retry states; preserve upload and ingest API behavior | P1/P2 |
| Governance and ops | `/approvals`, `/evaluations`, `/debug` | Approval cards, evaluation dialogs/runs, debug inspector | AlertDialog for decisions, Form/Dialog, Tabs/Table, Badge, Alert and explicit loading/empty/error states | P2 |
| Integrations | `/integrations` | OAuth connection cards, connect/disconnect, inline error | PageHeader, Card, Button, Badge, Alert, confirmation where destructive; preserve OAuth URLs and state | P2 |
| Settings | `/settings/profile`, `/settings/members`, `/settings/api-keys`, `/settings/quotas` | Manual forms/cards and native confirm buttons | Form, Label, Input, Select/Switch as appropriate, Table/list, AlertDialog, Alert, Skeleton, Sonner | P2 |
| Authentication | `/login`, `/register`, `/oauth/callback/[provider]` | Manual auth forms and redirect flow | Form semantics, Input, Label, Card, Button, Alert; preserve fetch endpoints, token storage, redirects | P2 |

## 4. Design system rules

### Tokens

- Use semantic CSS variables and Tailwind semantic utilities; no raw hex/rgb values in page components.
- Preserve dark-first behavior and light theme parity.
- Primary accent: desaturated emerald. Status colors are semantic and must not be the only signal:
  - success: positive completion/connected/active state plus text or icon;
  - warning: pending/observe/attention state plus text;
  - destructive: failed/rejected/delete/error state plus text and recovery action;
  - info: explanatory/informational state.
- Keep `--radius` as the base radius and use a documented scale: controls use the small/medium token, cards and dialogs use the large token, pills only for statuses/badges.
- Use existing shadow/elevation tokens. Avoid adding per-page shadows or decorative glow.

### Typography

- Continue using the existing `next/font` setup and semantic font variables.
- Body text: minimum 16px where practical, `leading-relaxed` for longer prose, and a readable measure around 60–75 characters on desktop.
- Page title: one clear `h1`, responsive `text-2xl` to `text-4xl`, weight 600–700.
- Section title: `h2`, generally 18–20px, weight 600.
- Labels and metadata: 12–14px, never the only place where essential meaning is communicated.
- Numeric, token, ID, and code values use tabular/mono styling where it improves scanning.
- Avoid all-caps tracking for normal content; reserve it for small labels/status metadata.

### Layout and spacing

- Main content uses a centered `max-w-7xl` container with mobile gutters and wider desktop gutters.
- Page rhythm: `space-y-8` for major sections, `space-y-6` for related groups, `gap-4`/`gap-6` for grids, and `gap-2`/`gap-3` within controls.
- Use CSS Grid for page-level multi-column layouts. Every multi-column layout explicitly collapses below `md`.
- No intentional horizontal overflow on mobile. Wide data tables may use a labeled, contained horizontal scroll region.
- Sticky shell elements reserve their own space; mobile uses `min-h-dvh` where full viewport behavior is needed.
- Primary actions appear in the PageHeader or the first relevant section; secondary actions use outline/ghost variants.

### Card rules

- Cards group content or communicate elevation; not every section needs a card.
- Use one surface language per page: plain grouped sections for dense data, Card for bounded content, Dialog/Sheet for transient flows.
- Avoid nested cards and excessive `rounded-xl` wrappers.
- Interactive cards must have keyboard-accessible links/buttons, visible focus, hover and pressed feedback.

### Interaction and accessibility

- Use semantic `button`, `a`, `label`, headings, and form associations; no clickable divs when a primitive exists.
- Icon-only controls require an accessible label and tooltip where useful.
- Minimum interactive target is approximately 44px, with at least 8px separation for adjacent controls.
- Dialogs need title, description where context is needed, close behavior, focus management, loading state, and unsaved-data considerations.
- Destructive actions use AlertDialog, not `window.confirm`.
- Forms show visible labels, helper text when needed, inline validation below the field, disabled/loading submit state, and an actionable error state.
- Preserve visible focus rings and keyboard access. Respect `prefers-reduced-motion` and avoid animation that changes layout.

## 5. Architecture and component boundaries

### UI primitives

`components/ui` contains only shadcn-compatible primitives and their token-level customization. Add a primitive only when an audited consumer needs it. Do not create `CustomButton`, `CustomModal`, `CustomDropdown`, or another primitive alias.

### Layout

- `components/layout/AppShell.tsx`: private/public shell boundary and content frame.
- `components/layout/AppSidebar.tsx`: desktop navigation, groups, active state, approval badge, collapse behavior.
- `components/layout/MobileNav.tsx`: Sheet-based mobile navigation.
- `components/layout/AppHeader.tsx`: mobile menu trigger, route title/breadcrumb where appropriate, theme toggle.
- Keep auth gate, query client, prefetch map, and navigation behavior semantically unchanged; extract them without changing inputs or API calls.

### Shared components

- `components/shared/PageHeader.tsx`
- `components/shared/SectionHeader.tsx`
- `components/shared/EmptyState.tsx`
- `components/shared/ErrorState.tsx`
- `components/shared/LoadingSkeleton.tsx`
- `components/shared/ConfirmDialog.tsx`
- `components/shared/StatusBadge.tsx`
- `components/shared/ListToolbar.tsx` only if at least two listing pages share the same search/filter behavior.

Existing shared components should be migrated or retained rather than duplicated. Compatibility exports may be kept temporarily while imports are migrated.

### Feature components

Retain or improve domain components such as AgentCard, ChatMessageItem, MarkdownRenderer, WorkflowNodeCard, WorkflowConsole, OrgSwitcher, and feature forms. Their visual primitives must come from `components/ui`; their business logic and data contracts remain in existing hooks/stores/API layers.

## 6. Phased implementation plan

### Phase 1 — Audit and inventory

- Verify every route, layout, component, form, table, modal, and loading/empty/error state.
- Record actual consumers before adding a primitive or dependency.
- Run baseline typecheck, lint, and build; preserve baseline failures separately from regressions.
- Check running app availability and inspect critical routes when possible.

### Phase 2 — Foundation

- Normalize CSS variables, theme parity, typography, spacing, radius, focus, disabled, hover, active, and reduced-motion states.
- Resolve the source-of-truth CSS file and avoid duplicate unused styling.
- Add only the shadcn primitives required by the first vertical slice and foundation consumers.
- Verify foundation with typecheck and build.

### Phase 3 — App shell

- Extract shell components from `app/layout.tsx`.
- Replace hand-built mobile overlay with Sheet-compatible navigation.
- Preserve route activation, prefetching, auth redirect, organization/user controls, theme toggle, and pending approval count.
- Verify desktop collapsed/expanded and mobile open/close keyboard behavior.

### Phase 4 — Shared components

- Standardize PageHeader, EmptyState, ErrorState, LoadingSkeleton, ConfirmDialog, StatusBadge, and form section patterns.
- Migrate existing consumers without changing API callbacks.
- Verify typecheck/build before continuing.

### Phase 5 — Dashboard vertical slice

- Refactor `/` end-to-end as the reference page.
- Include loading, empty, API error/retry, responsive stats, agent quick launch, usage table, and accessible actions.
- Validate visual and interaction rules at mobile and desktop widths.

### Phase 6 — Listing and form groups

- Refactor providers, models, MCP, files, workspace, evaluations, approvals, debug, integrations, and settings in small page groups.
- Add Form/Select/Checkbox/Switch/DropdownMenu/AlertDialog only when required by the page being migrated.
- Preserve query keys, mutation callbacks, payload shapes, validation schemas, and permission behavior.

### Phase 7 — Chat and workflow

- Refactor only presentation boundaries around existing streaming and canvas logic.
- Do not rewrite SSE reducers, recovery, typewriter buffering, Zustand graph state, drag/drop behavior, node layout, or run lifecycle.
- Use shadcn primitives for composer, action controls, status indicators, logs, dialogs, and responsive panels.
- Verify stream interruption, reattach, approval, cancel, save, run, and error flows.

### Phase 8 — QA and cleanup

- Run accessibility/responsive audit, remove duplicate primitives and dead CSS, inspect console/runtime warnings.
- Test 360/390/768/1280/1440px, keyboard navigation, reduced motion, light/dark themes, and narrow table behavior.
- Run typecheck, lint, repository tests if present, and production build. Fix regressions before reporting.

## 7. Behavior preservation contract

The following are explicitly immutable unless a bug prevents compilation or accessibility:

- Route paths, URL parameters, deep links, redirects, and browser history behavior.
- REST endpoints, request/response payloads, query keys, mutation invalidation, and API error handling semantics.
- Auth token storage/refresh, auth gate, OAuth callback behavior, organization selection, and permissions.
- Zod validation rules and domain constraints.
- CRUD behavior for agents, providers, models, MCP servers, files, evaluations, members, keys, quotas, and workflows.
- Chat sessions, SSE event handling, streaming/recovery/cancel behavior, model selection, tool calls, and approval decisions.
- Workflow graph editing, node/edge behavior, run streaming, logs, and durable run polling.

## 8. Verification gates

After each major phase:

1. Run `npm run typecheck`.
2. Run `npm run lint` using the repository's configured command; if the command is incompatible with the installed Next version, record and resolve the configuration issue without hiding lint failures.
3. Run `npm run build` at foundation, shell, dashboard, and final gates.
4. Run available tests or targeted smoke checks for changed behavior.
5. For UI phases, inspect critical routes at mobile and desktop widths and check console errors.

Final report must list changed routes/components, shadcn primitives added/used, domain-specific custom components retained, behavior preserved, commands/results, and any unresolved issues with reasons.

## 9. Risks and mitigations

- **Risk: broad rewrite breaks business behavior.** Mitigation: small vertical slices, preserve hooks/stores/API code, and validate after each phase.
- **Risk: dependency sprawl.** Mitigation: add primitives on demand only, pin versions, and reuse current Radix dependencies where possible.
- **Risk: chat/workflow regressions.** Mitigation: postpone these surfaces and change only presentation components around stable streaming/canvas logic.
- **Risk: visual inconsistency during migration.** Mitigation: foundation and shell first, then use the Dashboard as the reference page and migrate shared patterns.
- **Risk: accessibility regressions hidden by visual polish.** Mitigation: explicit keyboard, labels, focus, target-size, contrast, reduced-motion, and error-state checks at every page group.
