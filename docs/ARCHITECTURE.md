# OpenAgent — Architecture

> **OpenAgent** is a personal **multi-agent OS**. A layered, scalable **FastAPI**
> backend talks to a **Next.js** frontend (Tailwind + shadcn/ui + Zod + Zustand
> + TanStack Query). One OpenAI-compatible LLM driver. A **graph-based
> multi-agent workflow engine** (parallel, not sequential).

This is a deliberate, reduced reimagining of OpenFang (the Rust Agent OS): keep
the useful core, make it hackable and scalable for one person.

---

> This document describes the original v1/single-user architecture. For the
> current multi-user AgentOS v2 architecture, use
> `docs/agentos-v2/ARCHITECTURE.md`.

## 1. Design Principles

1. **Layered backend for maintainability & scale**
   `API (routes) → Service (business logic) → Repository (data access) → Model (ORM)`.
   No business logic in routers; no SQL in services. Swap DB/LLM/transport without
   touching the API contract.
2. **Contract-first schemas** — Pydantic request/response separated from ORM
   models. The frontend mirrors them with Zod.
3. **Single source of truth for types** — backend `schemas/`, frontend `lib/schemas.ts`
   (Zod) and `types/index.ts` are kept in sync.
4. **Async everywhere** — `asyncio` + async SQLAlchemy + async OpenAI client.
   Workflow nodes run concurrently with `asyncio.gather`.
5. **Database-agnostic** — SQLite (dev) via `aiosqlite`; migrate to Postgres by
   changing `OPENAGENT_DB_URL` + the driver. Schema managed by **Alembic**.
6. **Stateless API, stateful engine** — REST endpoints are stateless; long runs
   (chat stream, workflow) push progress over SSE/WebSocket.

---

## 2. Tech Stack

| Layer | Choice |
|-------|--------|
| Language (BE) | Python ≥ 3.11 |
| Web framework | FastAPI + Uvicorn |
| API style | REST (JSON) + SSE for streaming |
| ORM / Migrations | SQLAlchemy 2.0 (async) + Alembic |
| DB | SQLite (dev) → Postgres (prod-ready) |
| LLM | `openai` SDK (OpenAI-compatible only) |
| MCP | `mcp` Python SDK (client) |
| Config | `pydantic-settings` |
| Lint/format | Ruff |
| Tests | pytest + pytest-asyncio |

| Layer | Choice |
|-------|--------|
| Language (FE) | TypeScript |
| Framework | Next.js 15 (App Router) |
| Styling | Tailwind CSS + shadcn/ui |
| Validation | Zod |
| State | Zustand (client state) |
| Server state / fetch | TanStack Query |
| Forms | React Hook Form + Zod resolvers |
| Toast/UX | Sonner, Lucide icons |

---

## 3. Repository Layout

```
open-agent/
├── README.md
├── docs/
│   ├── ARCHITECTURE.md        # this file
│   ├── database-schema.md     # full DB schema
│   ├── api-reference.md       # all REST endpoints
│   └── modules/               # per-module functional design
│       ├── providers.md  models.md  agents.md  tools.md
│       ├── mcp.md  workflows.md  chat.md  debug.md  compactor.md
├── backend/
│   ├── pyproject.toml
│   ├── alembic.ini  alembic/  # migrations
│   ├── app/
│   │   ├── main.py            # app factory, CORS, lifespan, router mount
│   │   ├── config.py          # Settings (pydantic-settings)
│   │   ├── dependencies.py    # DI: get_db, get_api_key, get_llm_client
│   │   ├── db/                # base.py (Base, engine), session.py (get_db)
│   │   ├── models/            # SQLAlchemy ORM (provider, model, agent, mcp,
│   │   │                     #   workflow, session, message, usage)
│   │   ├── schemas/           # Pydantic v2 (request/response)
│   │   ├── repositories/      # data-access (one per entity + base)
│   │   ├── services/          # business logic (one per domain)
│   │   ├── core/              # engine (no HTTP)
│   │   │   ├── llm.py         # OpenAI-compatible client, streaming, cost
│   │   │   ├── agent_loop.py  # run one agent (tool-call loop)
│   │   │   ├── tools/         # registry + builtins (read_attachment,
│   │   │   │                 #   call_agent, web_fetch, memory, types)
│   │   │   ├── workflow/      # engine.py (graph DAG runner)
│   │   │   ├── compactor.py   # session summarization
│   │   │   └── security.py    # capability gate, safe_path, safe_url
│   │   ├── mcp/               # client.py (MCP connection + tool proxy)
│   │   └── api/
│   │       └── v1/
│   │           ├── router.py  # aggregates route modules
│   │           └── routes/     # providers, models, agents, mcp,
│   │                           #   workflows, chat, debug
│   ├── tests/
│   └── scripts/run.py
└── frontend/
    ├── package.json
    ├── next.config.mjs        # /api proxy → :8000
    ├── tailwind.config.ts  components.json  tsconfig.json
    ├── app/                   # routes: /, /providers, /models, /agents,
    │                         #   /mcp, /workflows, /chat, /debug
    ├── components/            # ui/ (shadcn), layout/, agents/, workflows/, chat/
    ├── lib/                   # api.ts (fetch), schemas.ts (zod), utils.ts
    ├── stores/               # zustand: agent, workflow, chat
    ├── hooks/                # tanstack-query: useAgents, useWorkflows, useChat
    └── types/index.ts
```

---

## 4. Request Lifecycle (layered)

```
HTTP request
   │
   ▼
api/v1/routes/X.py  (FastAPI router)
   │  - validate request body with Pydantic schema
   │  - resolve deps (get_db, get_api_key, get_llm_client)
   ▼
services/X_service.py  (business logic)
   │  - orchestrates repositories + core engine
   │  - transactions, validation rules, side-effects
   ▼
repositories/X_repo.py  (data access)
   │  - SQLAlchemy async sessions, queries
   ▼
models/*.py  (ORM rows)  ──►  SQLite / Postgres
   │
   ▼
response: Pydantic response schema  ──►  JSON
```

**Why this scales**: each layer is independently testable; repositories can be
swapped (e.g., caching layer); services compose engines; routers stay thin. The
OpenAI client, DB driver, and MCP servers are all injected via `dependencies.py`.

---

## 5. Cross-Cutting Concerns

- **Auth**: `dependencies.get_api_key` — if `OPENAGENT_API_KEY` is empty, only
  loopback is allowed; otherwise a Bearer token is required. Single local user,
  not multi-tenant (v1).
- **CORS**: configured for `OPENAGENT_CORS_ORIGINS` (frontend dev port 3000).
- **Migrations**: Alembic; `scripts/run.py` runs `alembic upgrade head` then
  starts uvicorn + seeds default provider/model.
- **Streaming**: chat + workflow progress use SSE (`text/event-stream`).
- **Observability**: structured logging (rich); `debug` module exposes raw state.

---

## 6. Data Flow — Chat

```
POST /api/agents/{id}/message
  → chat_service.send(agent_id, session_id?, message, stream)
      → agent_service.load(agent) + model_service.resolve(model)
      → session_repo.load_or_create(session)
      → if over budget: compactor.compact(session)
      → agent_loop.run(agent, history, tools, llm_client):
            loop (≤ max_iterations):
               resp = llm_client.chat(system, history, tool_schemas)
               if no tool_calls: break
               for call in resp.tool_calls:
                  tool = registry.get(call.name)   # capability gate
                  result = await tool.execute(args, ctx)
                  history.append(tool_result)
      → session_repo.persist(messages)
      → usage_repo.record(tokens, cost, model)
      → return / stream AgentLoopResult
```

## 7. Data Flow — Workflow (multi-agent graph)

See `docs/modules/workflows.md`. In short: a `Workflow` is a **DAG** of nodes
(`input`, `agent`, `tool`, `merge`, `output`). The `WorkflowEngine` topologically
schedules nodes and runs all dependency-satisfied nodes **concurrently** with
`asyncio.gather`, supports fan-out/fan-in and conditional edges, and emits
progress events. This is the deliberate upgrade over OpenFang's linear pipeline.

---

## 8. Module Map (quick)

| Domain | Routes | Service | Repository | Model | Core |
|--------|--------|---------|------------|-------|------|
| Providers | `routes/providers.py` | `provider_service` | `provider_repo` | `Provider` | — |
| Models | `routes/models.py` | `model_service` | `model_repo` | `Model` | — |
| Agents | `routes/agents.py` | `agent_service` | `agent_repo` | `Agent` | `agent_loop` |
| Tools | (used by agent_loop) | — | — | — | `core/tools/*` |
| MCP | `routes/mcp.py` | `mcp_service` | `mcp_repo` | `McpServer`,`McpTool` | `mcp/client` |
| Workflows | `routes/workflows.py` | `workflow_service` | `workflow_repo` | `Workflow`,`WfNode`,`WfEdge` | `core/workflow/engine` |
| Chat | `routes/chat.py` | `chat_service` | `session_repo` | `Session`,`Message` | `agent_loop`,`llm` |
| Debug | `routes/debug.py` | `debug_service` | `session_repo`,`usage_repo` | `UsageEvent` | — |
| Compactor | (used by chat/loop) | — | `session_repo` | `Message` | `core/compactor` |

Detailed per-module design lives in `docs/modules/*`.
