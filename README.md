# OpenAgent

> **AgentOS v2** is the current architecture: multi-user, RBAC, guardrailed,
> observable, deployable. See [`docs/agentos-v2/ARCHITECTURE.md`](docs/agentos-v2/ARCHITECTURE.md)
> for the target design and [`docs/agentos-v2/IMPLEMENTATION_PLAN.md`](docs/agentos-v2/IMPLEMENTATION_PLAN.md)
> for the milestone-by-milestone rollout (M0–M12, tenant quotas is the latest).
> This root README covers day-to-day orientation across the whole repo.

A **multi-agent OS**: layered **FastAPI** backend (Python, async SQLAlchemy 2.0)
+ **Next.js** frontend (Tailwind + shadcn/ui + Zod + Zustand + TanStack Query),
with OpenAI-compatible LLM access, a **graph-based multi-agent workflow engine**
(parallel fan-out/fan-in — not just a sequential pipeline), and three standalone
**MCP microservices** (RAG retrieval, Google Drive, Customer Intelligence) that
plug in over the MCP protocol without backend provider code.

---

## What it does

**Core**
- **Providers / Models** — connect OpenAI, OpenRouter, Ollama, Gemini, Anthropic, OpenCode Zen, DeepSeek, or custom OpenAI-compatible endpoints; discover and activate models per organization.
- **Agents** — system prompt + model + granted tool set + risk-tiered
  capabilities; versioned **releases** with an evaluation quality gate before
  publish.
- **Tools** — `read_attachment`, `write_file` / `list_dir` / `search_files`,
  `call_agent` (delegate to another agent as an audited `Task`), `web_fetch`,
  `run_shell` (sandboxed, requires approval), `memory_store` / `memory_recall`,
  plus any tool exposed by a connected MCP server.
- **Workflows** — connect agents/tools into a **DAG** that runs in parallel
  (wavefront scheduler, `asyncio.gather` fan-out/fan-in, conditional edges),
  with durable `WorkflowRun`/`WorkflowNodeRun` checkpoints and an optional
  queued execution mode for scaling across worker processes.
- **Chat** — streaming (SSE) chat with any agent, from the UI or REST.
- **Debug** — inspect messages, tool calls, token usage, latency, and the
  subagent delegation tree.
- **Evaluations** — suites/datasets/graders that score agent releases;
  publishing a release is blocked if it fails the pass-rate gate.
- **Compactor** — summarize long sessions to fit the context window.

**Platform (AgentOS v2)**
- **Multi-tenant**: Organization → Membership → Role, enforced at the
  repository layer (every query is scoped by `org_id`).
- **AuthN/AuthZ**: JWT access + rotating refresh tokens, OAuth2/OIDC login,
  API keys for machine-to-machine, static role→permission matrix
  (`platform_admin` / `org_admin` / `operator` / `user`).
- **Guardrails**: prompt-injection filter, secret/PII scanner, loop &
  cost/wall-clock circuit breakers, human-in-the-loop approval gate, append-only
  audit log.
- **Quotas**: per-org request/resource/storage limits enforced via a Redis
  Lua-script sliding window, with an observe-only mode and fail-open/closed
  policy per operation type.
- **Sandbox**: hardened Docker execution for `run_shell` (`--network none`,
  memory/cpu/pids limits, read-only rootfs, seccomp, hard timeout).
- **Observability**: `structlog` JSON logs, OpenTelemetry tracing, Prometheus
  metrics, Grafana dashboards, Loki log aggregation — all wired through
  `trace_id`/`run_id`.

---

## Stack

| Layer | Choice |
|-------|--------|
| Backend | Python ≥ 3.10, FastAPI, SQLAlchemy 2.0 (async) + Alembic, SQLite (dev) / Postgres (`asyncpg`) |
| Auth | JWT (`pyjwt`), Argon2 password hashing, OAuth2/OIDC (`authlib`) |
| Queue | Redis + `arq` (durable agent/workflow jobs, quota backend) |
| Vector DB | Qdrant (via `rag-service`) |
| LLM | Provider driver registry: OpenAI-compatible + native Anthropic/Gemini drivers |
| MCP | `mcp` Python SDK — backend is a client; `rag-service` and `customer-intelligence-mcp` are servers |
| Sandbox | Docker (hardened container per tool execution) |
| Observability | `structlog`, OpenTelemetry, Prometheus, Grafana, Loki |
| Frontend | Next.js 15 (App Router), React 19, Tailwind, shadcn/ui, Zod, Zustand, TanStack Query |

---

## Structure

```
open-agent/
├── docs/                 # ARCHITECTURE, database-schema, api-reference, modules/*, agentos-v2/*
├── backend/              # FastAPI: app/{api,core,db,evals,mcp,models,repositories,schemas,services}
├── frontend/              # Next.js: app/, components/, lib/, stores/, hooks/, types/
├── rag-service/           # Standalone RAG microservice (MCP server + REST admin API)
├── customer-intelligence-mcp/ # Stateless real email/calendar/Drive/research MCP connector
├── observability/         # Grafana dashboards + Prometheus config
├── scripts/               # Root-level e2e smoke tests (agent releases, evaluations, tenant quotas)
└── docker-compose.yml     # postgres, redis, api, worker, frontend, qdrant, rag-service,
                            # customer-intelligence-mcp, prometheus/grafana/loki/otel-collector (profile: observability)
```

Backend layering is strict `routes → services → repositories → models`;
cross-cutting concerns (auth, RBAC, guardrails, quotas, observability) attach
via FastAPI dependencies/middleware rather than living inside business logic.

Read [`docs/agentos-v2/ARCHITECTURE.md`](docs/agentos-v2/ARCHITECTURE.md) for
the full v2 design, [`docs/database-schema.md`](docs/database-schema.md) for
the DB, [`docs/api-reference.md`](docs/api-reference.md) for the REST surface,
and [`docs/modules/*`](docs/modules) for per-module design (agents, workflows,
tools, mcp, chat, debug, sandbox-tools, workspace-artifacts, compactor,
providers, models).

---

## Quick Start (dev)

### Docker Compose (full stack)

```bash
cp .env.example .env
docker compose up --build
```

Brings up `frontend` (:3000), `api` (:8000), `worker` (arq), `postgres`,
`redis`, `qdrant`, `rag-service`, and `customer-intelligence-mcp`. Use
`--profile observability` for `prometheus`/`grafana`/`loki`/`otel-collector`.

### Manual (backend + frontend only, SQLite)

```bash
# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env          # set OPENAI_API_KEY (+ OPENAI_BASE_URL if not OpenAI)
python scripts/run.py         # alembic upgrade + seed + uvicorn on :8000

# Frontend (separate terminal)
cd frontend
npm install
npm run dev                   # http://localhost:3000  (proxies /api → :8000)
```

`customer-intelligence-mcp` handles real Email, Calendar and Google Drive
connectors. Configure OAuth clients in `.env`, start the stack, then connect
accounts from `http://localhost:3000/integrations`.

---

## Testing

```bash
cd backend && pytest              # unit + integration (auth, authz, quotas, guardrails, workflows, evals, mcp, ...)
cd frontend && npm run typecheck && npm run lint && npm run build
python scripts/e2e_tenant_quotas.py   # e2e smoke tests against a running stack (frontend :3000 proxy)
python scripts/e2e_evaluations.py
python scripts/e2e_agent_releases.py
```

---

## Scope

**In:** providers, models, agents (+ versioned releases & evaluation gate),
MCP, chat, debug, compactor, graph workflows, multi-org RBAC, quotas,
guardrails, sandboxed tool execution, observability.
**Deliberately out (see [ARCHITECTURE.md §10](docs/agentos-v2/ARCHITECTURE.md)):**
dynamic ABAC/policy engine, Kubernetes manifests, microVM sandboxing, billing.

MIT.
