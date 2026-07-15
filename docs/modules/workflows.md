# Module: Workflows (Multi-Agent Graph) ★

> This is the headline feature: a **graph-based** multi-agent engine, not the
> sequential pipeline of OpenFang.

## Purpose
Compose agents (and tools) into a **directed acyclic graph (DAG)** that runs
**in parallel**, with fan-out, fan-in (`merge`), and conditional branching.
Each node uses its own Agent config, so a workflow naturally mixes heterogeneous
agents (researcher + writer + critic).

## Data Model
- `workflows` (`database-schema.md §2.6`): `name`, `graph` (JSON),
  `entry_node_id`.
- `graph` shape:
```json
{
  "nodes": [
    { "id": "n1", "kind": "input",   "config": { "inputs": { "topic": "AI agents" } } },
    { "id": "n2", "kind": "agent",   "ref": "<agent_id_or_name>", "config": {} },
    { "id": "n3", "kind": "agent",   "ref": "writer", "config": {} },
    { "id": "n4", "kind": "merge",   "config": { "mode": "concat|summary" } },
    { "id": "n5", "kind": "output",  "config": {} }
  ],
  "edges": [
    { "from": "n1", "to": "n2" },
    { "from": "n1", "to": "n3" },
    { "from": "n2", "to": "n4" },
    { "from": "n3", "to": "n4" },
    { "from": "n4", "to": "n5" }
  ]
}
```

### Node kinds
| kind | meaning | config |
|------|---------|--------|
| `input` | seed values / static inputs | `{ "inputs": {k:v} }` |
| `agent` | run an Agent (`ref` = id/name) | `{ "prompt_template"?: str }` (may interpolate upstream outputs) |
| `tool` | run a single builtin/MCP tool (advanced) | `{ "tool": "web_fetch", "args": {...} }` |
| `merge` | combine N inbound outputs | `{ "mode": "concat|summary" }` |
| `output` | terminal result node | `{}` |

### Edge
`{ "from", "to", "from_port"?, "to_port"?, "condition"? }`
- `condition` (optional): predicate on the source output, e.g.
  `{ "field": "label", "eq": "spam" }` → edge only taken when true (branching).

## API
| Method | Path | Body | Returns |
|--------|------|------|---------|
| GET | `/api/workflows` | — | list |
| POST | `/api/workflows` | `WorkflowCreate` (graph JSON) | created |
| GET/PUT/DELETE | `/api/workflows/{id}` | `WorkflowUpdate` | one |
| POST | `/api/workflows/{id}/run` | `{ "inputs"?, "stream": true }` | run (SSE) |

## Execution Algorithm (`core/workflow/engine.py`)
```
async def run_workflow(wf, initial_inputs, stream_cb):
    g = parse(wf.graph)
    validate_dag(g)                       # reject cycles
    values = {}                           # node_id -> output
    pending = { n.id: {} for n in g.nodes }  # collected inbound inputs
    indeg = compute_indegree(g)
    ready = [n for n in g.nodes if indeg[n.id] == 0]

    while ready:
        # run ALL ready nodes CONCURRENTLY
        results = await asyncio.gather(*[
            execute_node(n, inputs_for(n, pending)) for n in ready
        ], return_exceptions=True)

        for n, out in zip(ready, results):
            if isinstance(out, Exception):
                emit(error, node_id=n.id); mark_failed(n); continue
            values[n.id] = out
            emit(node_completed, node_id=n.id, output=out)
            for e in edges_from(n.id):
                if not edge_enabled(e, out): continue     # condition check
                indeg[e.to] -= 1
                pending[e.to][port(e)] = out
                if indeg[e.to] == 0: ready.append(node(e.to))
        ready = [n for n in ready if indeg[n.id] == 0]     # refresh

    return collect_outputs(g, values)     # outputs of kind=="output"
```

### `execute_node`
- `input`: returns `config.inputs` merged with `initial_inputs`.
- `agent`: load agent, build prompt (interpolate `{{node_x.field}}` from
  `pending`), run `agent_loop.run()` (same engine as chat), return final text.
- `tool`: execute the single tool via the registry.
- `merge`: gather all inbound `pending` values → `concat` (join texts) or
  `summary` (one cheap LLM call to synthesize).
- `output`: passes its single inbound value through.

### Key properties (the improvement)
| Capability | OpenFang (sequential) | OpenAgent (graph) |
|------------|-----------------------|------------------|
| Parallel agents | ✗ | ✓ `asyncio.gather` |
| Fan-out / fan-in | ✗ | ✓ `merge` node |
| Conditional branch | ✗ (linear) | ✓ `condition` on edge |
| Per-step model/agent | limited | ✓ each node = its own Agent |
| Visual builder | n/a | ✓ Next.js node editor |

### Error handling
- A failed node marks the workflow failed but lets already-running siblings
  finish (`return_exceptions=True`).
- Errors are attached to the node and streamed as `event: error`.
- Cycles are rejected at validation (DAG only).

### Streaming
`stream_cb`/`stream:true` emits SSE: `node_started`, `node_completed`,
`workflow_done`, `error`. The UI renders live node status on the graph.

## Layers
- `routes/workflows.py` — validate `WorkflowCreate` (DAG sanity: unique ids,
  valid kinds, refs exist, no cycles).
- `services/workflow_service.py` — orchestrates `WorkflowEngine`, records usage.
- `repositories/workflow_repo.py` — CRUD.
- `core/workflow/engine.py` — pure execution (no HTTP).

## Frontend — Workflow Builder
- `app/workflows/page.tsx`: list + editor.
- `components/workflows/editor.tsx`: **graph canvas** (e.g. React Flow) with
  node palette (Input / Agent / Merge / Output), drag to connect edges,
  click node → config panel (agent `<Select>`, merge mode, edge condition).
- `components/workflows/run-panel.tsx`: "Run" button → SSE stream; nodes light
  up `running`/`done`/`error`; final output shown.
- `stores/workflow-store.ts` (Zustand): holds the in-editing graph, selection.
- `hooks/useWorkflows.ts`: list, create, `useRunWorkflow` (SSE consumer).
- Zod: `WorkflowGraph` schema (nodes/edges) validates before save.

## Example: Researcher → Writer (parallel) → Merge
```
input(topic) ─┬─> agent(researcher) ─┐
               └─> agent(analyst)  ─┴─> merge ─> output
```
Both agents run at the same time; `merge` waits for both, concatenates, and the
output node returns the combined brief.
