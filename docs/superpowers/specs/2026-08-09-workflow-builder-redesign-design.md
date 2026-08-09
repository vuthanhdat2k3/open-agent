# Workflow Builder Redesign — Design Spec

Date: 2026-08-09
Status: Approved (pending spec self-review sign-off)

## 1. Context

The current workflow builder (`frontend/app/workflows/page.tsx`,
`components/workflows/workflow-node-card.tsx`) is a fully hand-rolled canvas:
node dragging via raw `mousedown`/`mousemove`/`mouseup` listeners, edges drawn
as manual SVG `<path>` elements, no zoom/pan, no minimap, coordinates computed
by hand from `getBoundingClientRect()`. It works but looks and feels dated
next to modern AI workflow editors (e.g. React Flow's "AI Workflow Editor"
template, workflowbuilder.io).

Goal: redesign the workflow builder to look and feel modern — drag-and-drop
node palette, smooth bezier connections, animated execution feedback, minimap,
zoom controls, dark dot-grid canvas — while keeping the existing backend API,
graph schema (`GNode`/`GEdge`), execution engine, and SSE run-streaming logic
completely unchanged. This is a frontend-only visual/interaction redesign.

## 2. Decisions from research

Two reference products were evaluated:

- **React Flow (`@xyflow/react`)** — MIT-licensed node-based UI library. Its
  companion "React Flow UI" catalog (shadcn-CLI-installable components like
  Base Node, Handle, Button Edge, Controls, MiniMap) is free; only the fully
  assembled "AI Workflow Editor" *template* is a paid Pro asset. We will build
  our own custom node/edge components in the same visual spirit rather than
  buying the template.
- **workflowbuilder.io** — a commercial SDK that ships its own backend
  (Hono + Temporal engine adapter). Adopting it would mean replacing the
  project's existing FastAPI workflow engine (`app/core/workflow/engine.py`,
  durable `WorkflowRun`/`WorkflowNodeRun` checkpoints). Rejected — out of
  scope and would drop working infrastructure for no benefit.

**Chosen approach:** adopt `@xyflow/react` as the canvas engine, keep the
existing FastAPI backend/API untouched, and design custom-styled nodes/edges
matching the project's existing dark glass/shadow-3d visual language.

## 3. Scope

**In scope:**
- Replace the hand-rolled canvas in `app/workflows/page.tsx` with a
  `@xyflow/react`-based canvas.
- New components: `workflow-canvas.tsx`, `workflow-node-palette.tsx`,
  per-kind custom node components, `workflow-custom-edge.tsx`.
- Drag-and-drop node creation from a palette sidebar (replacing the current
  "Add node" button list).
- Add `approval` and `sub_workflow` as first-class node kinds in the palette
  and config panel (backend already supports both — see §6).
- Minimap, zoom/pan controls, animated running-state feedback on nodes and
  edges.
- Config panel becomes an overlay/drawer instead of an always-visible column.

**Out of scope (unchanged):**
- Backend workflow engine, API routes, DB schema.
- SSE run-streaming protocol and event handling logic in `page.tsx`.
- Zustand store shape (`useWorkflowStore`) beyond what's needed for React
  Flow compatibility (position format is already `{x, y}` — compatible as-is).
- Auto-layout algorithm (keep existing BFS layer algorithm; only the
  rendering changes).
- `WorkflowConsole` (run log panel) — kept as-is, same position below canvas.

## 4. Architecture

```
frontend/components/workflows/
├── workflow-canvas.tsx          # ReactFlow wrapper: nodes, edges, background,
│                                 # controls, minimap, drop handling
├── workflow-node-palette.tsx    # Left sidebar, draggable node type list
├── workflow-node-types.tsx      # Custom node components per kind (registered
│                                 # as ReactFlow nodeTypes)
├── workflow-custom-edge.tsx     # Custom edge: bezier path + delete button +
│                                 # running-state animation
├── workflow-node-config.tsx     # Right-side drawer: per-kind config form
│                                 # (extracted from page.tsx inline JSX)
└── workflow-console.tsx         # unchanged
```

`app/workflows/page.tsx` keeps all data/state logic (hooks, SSE run handler,
save/load, AI-generate) but delegates rendering to `WorkflowCanvas` +
`WorkflowNodePalette` + `WorkflowNodeConfig` instead of inline canvas markup.

Dependency added: `@xyflow/react` (pinned exact version, MIT license).

## 5. Canvas & visual design

**Background:** dark canvas, `Background` component with `variant="dots"`,
larger dot size (20px) and gap than the current 16px pattern so it stays
uncluttered with more nodes on screen.

**Node card:** ~200×88px (up from 160×70 to fit a larger icon), `rounded-2xl`,
`bg-card/90 backdrop-blur-xl`. A 32px icon sits in a circular badge. The
project's design system is intentionally monochrome (see `globals.css`: "one
monochrome palette, no second scale") — so kinds are NOT color-coded.
Instead each kind gets a distinct icon in a neutral `bg-muted/40
border-border/60` badge, and the `approval` kind (the one exception, since it
represents a safety/danger gate) uses the existing `warning` token for its
badge to stand out as a pause point:

| Kind | Icon | Badge |
|---|---|---|
| input | Box | neutral (muted) |
| agent | Bot | neutral (muted) |
| tool | Wrench | neutral (muted) |
| merge | GitMerge | neutral (muted) |
| output | LogOut | neutral (muted) |
| approval | ShieldAlert | warning |
| sub_workflow | Workflow | neutral (muted) |

**Status styling** (reuses existing `nodeStatus` state, restyled):
- idle: default border, no glow.
- running: info-colored border + soft glow (`animate-pulse-soft`, existing
  utility class).
- done: success-colored border, glow fades.
- error: destructive border + small `AlertCircle` badge overlay.

**Handles:** React Flow `<Handle>` components, restyled as small circular
dots, brighten on hover/connect-drag (native React Flow connection state).

**Edges:** custom edge component using `getBezierPath`. Default: subtle
border-colored stroke, width 2. Hover: brightens to primary + shows a delete
(×) button via `EdgeLabelRenderer` at the midpoint (replaces the current
hand-drawn `<g>` click target). While the edge's source node is `running`:
stroke switches to info color with an animated dashed stroke (CSS
`stroke-dashoffset` keyframe, slow enough to read as "flow" rather than noise).
Briefly success-colored after the source node completes, then reverts to
default.

**Palette sidebar (left, ~220px, collapsible to icon-only):** each entry has
icon + label + one-line description (e.g. "Agent — invoke an agent"). Items
are `draggable`; drop is handled via ReactFlow's `screenToFlowPosition` API
(replacing manual `getBoundingClientRect` math) so drop position is correct
regardless of current zoom/pan.

**Top toolbar:** unchanged `PageHeader` actions (New/Load/Auto-Layout/AI
Generate/Save). Added: a ReactFlow `<Panel>` (top-right, floating over canvas)
with zoom in/out/fit-view (from `<Controls>`) and a minimap show/hide toggle.

**Page layout:** palette (fixed ~220px) + canvas (flexible width, height
`calc(100vh - 260px)`, min 500px, replacing the previous fixed 500px/4-col
grid) + config panel as a slide-in drawer on the right when a node is
selected (instead of an always-visible column), so the canvas has more room
when nothing is selected. `WorkflowConsole` stays below, full width.

## 6. New node kinds: `approval` and `sub_workflow`

Backend already executes both (`app/core/workflow/engine.py` lines ~310-338):

- **`approval`**: config field `tool_name` (optional, shown as context on the
  approval request). Executing this node raises `WorkflowWaitingApproval`,
  pausing the run until a decision is made via the existing `/approvals`
  routes. Config panel: single optional text input for `tool_name`, plus a
  static note: "Workflow will pause and wait for approval."
- **`sub_workflow`**: config field `workflow_id` (required) — must reference
  another workflow in the same org. Config panel: a `<Select>` populated from
  `useWorkflows()`, excluding the workflow currently being edited (avoid
  self-reference). Backend already validates existence and org match at
  execution time; no new backend validation is added here since this is a
  frontend-only redesign.

Both get palette entries and custom node card rendering per §5's table.

## 7. State & data flow (unchanged contracts)

- `useWorkflowStore` keeps its current shape (`nodes`, `edges`,
  `selectedNodeId`, `activeRunId`). Node `position` is already `{x, y}`,
  directly compatible with React Flow's `Node.position`.
- `GNode`/`GEdge` types are unchanged; React Flow nodes/edges are derived from
  them via a thin mapping layer inside `workflow-canvas.tsx` (kind → node
  `type`, `from_`/`to` → `source`/`target`), converting back to `GNode`/`GEdge`
  shape on any change before calling `setGraph`.
- SSE run-streaming handler in `page.tsx` (`run()` function) is untouched;
  it already updates `nodeStatus` by node id, which the new node components
  read the same way the old `WorkflowNodeCard` did.
- Auto-layout button keeps calling the existing BFS `layout()` function;
  only how positions are rendered changes.

## 8. Testing

- No backend changes, so no backend tests are added.
- Frontend: `npm run typecheck`, `npm run lint`, `npm run build` must pass.
- Manual verification checklist (since there's no existing frontend test
  runner for canvas interactions):
  - Drag each of the 7 node types from palette onto canvas at various zoom
    levels; verify drop position accuracy.
  - Connect two nodes by dragging from a source handle to a target handle.
  - Delete a node and an edge via their UI controls.
  - Select a node, verify the config drawer opens with the right fields per
    kind (including new `approval`/`sub_workflow` fields).
  - Run a saved workflow and verify running/done/error states animate
    correctly on nodes and their outgoing edges.
  - Toggle minimap and use zoom/fit-view controls.
  - Verify Save/Load/New/Auto-Layout/AI-Generate still work end-to-end.

## 9. Risks / open items

- `@xyflow/react` adds ~50-80kb gzipped to the frontend bundle — acceptable
  given it replaces hand-rolled canvas code and unlocks native zoom/pan/
  minimap/accessibility behavior.
- Existing saved workflows have `position` values computed by the old BFS
  layout in old coordinate spacing; they will render fine under React Flow
  (same `{x,y}` shape) but users may want to hit "Auto-Layout" once after
  migrating for tidier spacing under the new, larger node card size.
