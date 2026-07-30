# OpenAgent — Frontend Design System (MASTER)

Single source of truth for the UI. Every page-level change MUST read this file and
follow it exactly. Do not introduce new colors, radii, or component patterns beyond
what is specified here.

## Design Read
Developer-tool / multi-agent platform (B2B, technical users). "Terminal-adjacent",
precise, premium B2B SaaS tool with subtle 3D depth, tactile micro-interactions,
and controlled glassmorphism. Tailwind + shadcn-style tokens + **Fira Sans** (sans) /
**Fira Code** (mono) + a single desaturated **emerald** accent. Dark is the default theme.

Dials: **VARIANCE 7** (structured asymmetric depth, layered specular elevation) ·
**MOTION 7** (fluid spring dynamics `cubic-bezier(0.16, 1, 0.3, 1)`, staggered cascade reveals, micro-physics press feedback) ·
**DENSITY 4** (airy, generous spacing, balanced devtool data architecture).

Brand accent = desaturated emerald `--primary` (~52% sat). Status = success /
warning / info / destructive. **NO purple, NO neon glow, NO cream/brass palette,
NO emojis as icons (lucide only).** A subtle ambient emerald/info bloom with specular light is rendered
behind content in dark mode (do not re-add per-component glows).

## Rationale for Design System Upgrade (v2.0 Refactor)
- **Previous state (v1.0)**: VARIANCE 6 / MOTION 6 / DENSITY 4 — flat terminal aesthetic, basic card lift, linear-ish motion.
- **Upgraded state (v2.0)**: VARIANCE 7 / MOTION 7 / DENSITY 4 — elevated 3D depth, multi-layered specular highlights, tactile micro-spring physics, and 3D card perspective hover feedback.
- **Why**: Modern B2B dev tools (Linear, Railway, Supabase) achieve high perceived quality not through gaudy 3D models or neon glows, but through **layered elevation (shadows + specular borders + backdrop blur)** and **tactile spring feedback**. This upgrade delivers 3D depth while keeping zero bundle bloat and maintaining strict WCAG AA contrast.

## Tokens (wired in globals.css + tailwind.config.ts)
- Dark is the default theme (`html` has `class="dark"`). A light theme + toggle exist.
- Never hardcode hex/rgb. Use semantic utilities only:
  `bg-background bg-card text-foreground text-muted-foreground border-border`
  `bg-primary text-primary-foreground` `bg-secondary` `bg-accent` `bg-muted`
  `bg-destructive …` `bg-success text-success-foreground …`
  `bg-warning …` `bg-info …`
- Radius: single unified scale. `--radius: 0.75rem`. Buttons/inputs = `rounded-lg`, cards/
  dialogs = `rounded-xl` (dialogs `rounded-2xl`).
- 3D Shadow & Elevation Scale (use these tokens, not raw box-shadow):
  - `shadow-card` / `shadow-3d-card`: 3-layer card elevation with top specular highlight (`inset 0 1px 0 0 hsl(0 0% 100% / 0.08)` + ambient + key shadow).
  - `shadow-3d-elevated`: dynamic elevated state for hovered cards and floating panels.
  - `shadow-3d-floating`: modal/dialog elevation with wide diffusion.
  - `shadow-3d-pressed`: inset tactile shadow for active states.
  - `shadow-inner-edge`: inset specular highlight for glass edge refraction.
- Motion utilities (CSS + spring timing):
  - `animate-fade-in`, `animate-slide-up`, `animate-scale-in` — spring entrance animations.
  - `.stagger` — parent container cascading children with 40ms spring stagger.
  - `.card-lift`: 3D lift transform (`translateY(-3px) scale(1.005)`) with specular edge highlight.
  - `.active-tactile`: physical press feedback (`active:scale-[0.98] active:translate-y-0`).
  - Easing token: `ease-out-expo` (`cubic-bezier(0.16, 1, 0.3, 1)`) — spring physics across all transitions.
  - Global `prefers-reduced-motion` rule neutralizes motion automatically.

## Shell (app/layout.tsx — Deliberate Upgrade Logged)
- Collapsible left sidebar (`lg:w-64` / `lg:w-[76px]` collapsed) with frosted glass background (`bg-card/40 backdrop-blur-xl border-r border-border`), desaturated emerald active indicator pill (`bg-primary/10 text-primary shadow-inner-edge font-semibold`), active left bar indicator, and `aria-current="page"`.
- Mobile navigation drawer with backdrop blur and accessible dialog semantics.
- Sticky top header (`h-14`) with page title, theme toggle, and subtle glass border (`bg-background/80 backdrop-blur border-b border-border`).
- Centered content container (`max-w-7xl`), responsive padding, and `animate-fade-in` replay on route change.

## Reusable components (components/ui/ & components/)
- `PageHeader` — `{ icon, title, description?, actions? }`. Standard page header with 3D gradient icon badge.
- `EmptyState` — `{ icon?, title, description?, action? }`. Frosted glass zero-data container with scale-in entrance.
- `Skeleton` — Shimmer loading placeholder matching layout geometry.
- `Card`, `CardHeader`, `CardTitle`, `CardDescription`, `CardContent`, `CardFooter`. Accepts `glass?: boolean`.
- `Button` — `variant` (default/outline/secondary/ghost/destructive/link), `size` (default/sm/lg/icon), `loading`, `asChild`. 3D depth, specular highlight, hover lift, active press state.
- `Badge` — `variant`: default/secondary/outline/destructive/**success**/**warning**/**info**/success-outline/warning-outline/info-outline. Pill badges with specular borders.
- `Input`, `Textarea`, `Label` — Label ABOVE input. Ring focus glow on focus.
- `Select`, `Tabs`, `Slider` (from `@/components/ui/select`).
- `Dialog`, `DialogTrigger`, `DialogContent`, `DialogHeader`, `DialogTitle`, `DialogDescription`, `DialogFooter`, `DialogClose`.
- `Table`, `TableHeader`, `TableBody`, `TableRow`, `TableHead`, `TableCell`.

## Page Pattern Rules (Enforced across ALL 16 routes)
1. Header: `<PageHeader icon={…} title="…" description="…" actions={…} />`
2. Spacing: `<div className="space-y-8">` (or `space-y-6` for tight sections).
3. Loading: Render `<Skeleton>` blocks matching final card or table shape.
4. Empty state: Render `<EmptyState>` with explicit call to action.
5. Responsive Grids: `grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3` wrapped in `.stagger`.
6. Cards: Use `Card` with `glass` or `card-lift` for 3D elevation.
7. Tables: `Table` with `text-right tabular-nums font-mono` for numeric data.
8. Statuses: Use `Badge` variants (success, warning, info, destructive). Never hardcode raw color utility borders/backgrounds.
9. Interactive Forms / Modals: Inline validation, loading states on buttons (`loading={isPending}`).
10. Large Page Architecture: Split complex pages (`/agents`, `/chat`, `/workflows`) into modular components inside their respective subdirectories (`components/agents`, `components/chat`, `components/workflows`).

## Page Inventory (16 Routes Covered)
1. `/` (Dashboard) — 5 stat cards with 3D gradient icons + Usage analytics table.
2. `/agents` — Agent card grid + Modular New Agent Dialog (sub-components in `components/agents`).
3. `/chat` — 4-column multi-agent chat interface + streaming thread + composer (sub-components in `components/chat`).
4. `/workflows` — Interactive workflow graph editor + SSE run stream + node cards (sub-components in `components/workflows`).
5. `/providers` — AI Provider card grid + New Provider Dialog.
6. `/models` — Models directory list & metadata breakdown.
7. `/mcp` — MCP servers management & connection details.
8. `/files` — File uploads dropzone & uploaded file list.
9. `/evaluations` — Benchmark evaluation runs & status metrics.
10. `/debug` — Session & message inspector view.
11. `/settings/members` — Org team members & role management.
12. `/settings/api-keys` — Organization API keys management.
13. `/settings/quotas` — Usage quota limits & usage meters.
14. `/login` — Auth login card interface.
15. `/register` — Auth registration card interface.
16. `/oauth/callback/[provider]` — OAuth authentication callback loading & verification.

## Accessibility & Performance Guardrails
- **WCAG AA Contrast**: Text 4.5:1 minimum against cards and background.
- **Focus States**: Visible ring (`focus-visible:ring-2 focus-visible:ring-ring`).
- **Reduced Motion**: All CSS animations and transforms neutralized under `prefers-reduced-motion: reduce`.
- **Keyboard Navigation**: Full Tab order, ARIA attributes (`aria-current="page"`, `aria-label`, `aria-busy`).
- **No Heavy Libraries**: Native CSS 3D transforms + Framer Motion (where needed), zero WebGL/Three.js bundle bloat.
