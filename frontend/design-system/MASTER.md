# OpenAgent — Frontend Design System (MASTER)

Single source of truth for the UI. Every page-level change MUST read this file and
follow it exactly. Do not introduce new colors, radii, or component patterns beyond
what is specified here.

## Design Read
Developer-tool / multi-agent platform (B2B, technical users). "Terminal-adjacent",
precise, premium. Tailwind + shadcn-style tokens + **Fira Sans** (sans) / **Fira Code**
(mono) + a single refined **emerald** accent. Dark is the default theme.

Dials: VARIANCE 6 (clean, mostly-symmetric with intentional offset) · MOTION 6
(fluid CSS, spring-like easing, staggered reveals, reduced-motion respected) ·
DENSITY 4 (airy, generous spacing).

Brand accent = emerald `--primary` (desaturated, ~52% sat). Status = success /
warning / info / destructive. **NO purple, NO neon glow, NO cream/brass palette,
NO emojis as icons (lucide only).** A subtle ambient emerald/info bloom is rendered
behind content in dark mode (do not re-add per-component glows).

## Tokens (wired in globals.css + tailwind.config.ts)
- Dark is the default theme (html has `class="dark"`). A light theme + toggle exist.
- Never hardcode hex/rgb. Use semantic utilities only:
  `bg-background bg-card text-foreground text-muted-foreground border-border`
  `bg-primary text-primary-foreground` `bg-secondary` `bg-accent` `bg-muted`
  `bg-destructive …` `bg-success text-success-foreground …`
  `bg-warning …` `bg-info …`
- Radius: one scale. `--radius: 0.75rem`. Buttons/inputs = `rounded-lg`, cards/
  dialogs = `rounded-xl` (dialogs `rounded-2xl`).
- Shadows (use these, not raw box-shadow):
  - `shadow-card` — default elevation for cards/surfaces.
  - `shadow-diffuse` — softer, wide diffusion for floating/primary elements.
  - `shadow-inner-edge` — inset top highlight for glass/refraction edges.
- Motion utilities (CSS, already defined):
  - `animate-fade-in`, `animate-slide-up`, `animate-scale-in` — entrance animations.
  - `.stagger` — parent that fades/slides its children in with a 50ms cascade.
  - Easing token: `ease-out-expo` (cubic-bezier(0.16,1,0.3,1)) — use for
    `transition-*` on interactive elements.
  - Global `prefers-reduced-motion` rule neutralizes all motion automatically.

## Shell (app/layout.tsx — already built, do NOT touch)
Collapsible left sidebar (emerald active state + left bar + `aria-current`), mobile
drawer, top bar with page title + theme toggle. Content is centered, `max-w-7xl`,
responsive padding, and replays a fade-in on every route change.

## Reusable components (use these, do not reinvent)
- `PageHeader` — `{ icon, title, description?, actions? }`. Use at top of EVERY page.
- `EmptyState` — `{ icon?, title, description?, action? }`. For zero-data states.
- `Skeleton` — shimmer loading placeholder. Use for loading states, shaped like layout.
- `Card`, `CardHeader`, `CardTitle`, `CardDescription`, `CardContent`, `CardFooter`.
  `Card` accepts an optional `glass` prop for frosted surfaces.
- `Button` — `variant` (default/outline/secondary/ghost/destructive/link),
  `size` (default/sm/lg/icon), `loading`, `asChild` for `Link`. Has hover-lift +
  tactile press built in; do not add your own transform on top.
- `Badge` — `variant`: default/secondary/outline/destructive/**success**/**warning**/
  **info**/success-outline/warning-outline/info-outline.
- `Input`, `Textarea`, `Label` — label ABOVE input; never placeholder-only.
- `Select`, `Tabs`, `Slider` (from `@/components/ui/select`).
- `Dialog`, `DialogTrigger`, `DialogContent`, `DialogHeader`, `DialogTitle`,
  `DialogDescription`, `DialogFooter`, `DialogClose`.
- `Table`, `TableHeader`, `TableBody`, `TableRow`, `TableHead`, `TableCell`.

## Page pattern (every page)
1. `<PageHeader icon={…} title="…" description="…" actions={…} />`
2. Content region: `space-y-6` (or `space-y-8` for airy sections).
3. Loading: replace content with `<Skeleton>` blocks shaped like the final layout.
4. Empty: `<EmptyState icon={…} title="…" description="…" action={…} />`.
5. Lists: responsive grid `grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3`
   (or appropriate). Wrap the grid in `.stagger` for a cascade reveal. Cards show
   title + meta + actions; apply `card-lift` for hover elevation.
6. Tables: use `Table`. Numeric columns: `text-right tabular-nums font-mono`.
7. Status: use `Badge` variants, never raw `border-green-500` etc.
8. Async actions: `Button loading={mutate.isPending}` or local `loading` state;
   pair with toasts for feedback.
9. Confirm destructive actions (delete) — confirmation Dialog or clearly separated
   destructive `Button`.

## Motion rules (MOTION 6)
- Entrance: wrap lists/groups in `.stagger`, or add `animate-slide-up` to hero blocks.
  Keep entrances subtle (<= 0.5s, `ease-out-expo`).
- Hover: rely on `card-lift` (cards) and the Button's built-in lift — do not stack
  transforms.
- Tactile: Buttons already press (`active:scale-[0.98]`). For custom pressable
  elements add `active:scale-[0.98] transition-transform`.
- NEVER `window.addEventListener('scroll')`. NEVER animate `top/left/width/height` —
  use `transform`/`opacity` only.
- Respect `prefers-reduced-motion` (handled globally; your CSS animations are auto-
  disabled).

## Responsive rules (CRITICAL)
- No horizontal scroll on mobile (375px). Use `grid-cols-1` then scale up.
- Touch targets >= 40px (buttons are h-9/h-10). Gap >= 8px.
- Header actions wrap (`flex-wrap`) on small screens.

## Accessibility
- Every interactive element keyboard reachable + visible focus (ring token set).
- Form fields have `<Label>`; icon-only buttons have `aria-label`.
- `aria-current="page"` on active nav (handled in shell).
- Body text >= 16px equivalent (`text-sm` is the floor for secondary).

## Anti-patterns (forbidden)
- Raw color utilities (`border-green-500`, `bg-blue-500`, `text-emerald-500`, hex).
- Emoji as icons; mixing icon families (lucide only).
- Centered hero gimmicks; this is a product UI, not a landing page.
- Reintroducing a fixed-width, non-collapsible 256px sidebar.
- Decorative-only animation; every motion must be subtle + meaningful.
- Stacking transforms/animations that fight the built-in Button/Card motion.

## Per-page notes (preserve all data logic — only restyle)
- **Dashboard** (`/`): stat tiles grid (5) + usage summary table. Keep the 5 stat
  tiles (use `Card` + `card-lift` + `animate-scale-in`/stagger), keep usage table
  (use `Table`). Loading -> `Skeleton`; empty -> `EmptyState`.
- **Providers** (`/providers`): provider cards (name, default badge, base_url + env
  in mono, Test + Delete actions). New Provider dialog uses `ProviderForm`.
- **Models** (`/models`): list; show provider + context/price meta if available.
- **Agents** (`/agents`): list + New Agent dialog (name, description, model Select,
  system prompt Textarea, tools as toggle Badges, max_iterations Input, temperature
  Slider).
- **MCP** (`/mcp`): MCP server list; connect/manage dialog.
- **Chat** (`/chat`): agent picker + streaming message thread + composer. Keep the
  4-col layout logic; elevate message bubbles (user = `bg-primary`, assistant =
  `bg-card` border, tool = distinct treatment), add entrance on new messages.
- **Debug** (`/debug`): inspection view (sessions / messages / tool calls).
- **Workflows** (`/workflows`): graph editor. Keep node/edge logic. Replace raw
  `border-green-500/blue-500/red-500` node states with `border-success` / `border-info`
  / `border-destructive`. Use `PageHeader`, responsive 12-col -> stacked, `Card` for
  run output, `Badge` for status. Keep `useWorkflowStore` + SSE streaming intact.
