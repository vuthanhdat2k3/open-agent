# OpenAgent

> A personal **multi-agent OS**. Layered **FastAPI** backend (Python) + **Next.js**
> frontend (Tailwind + shadcn/ui + Zod + Zustand + TanStack Query). One
> OpenAI-compatible LLM driver. A **graph-based multi-agent workflow engine**
> (parallel — not sequential).

A reduced, hackable reimagining of OpenFang (the Rust Agent OS): keep the useful
core, make it scalable for one person.

---

## What it does

- **Providers / Models** — manage OpenAI-compatible endpoints + their models.
- **Agents** — system prompt + model + granted tool set.
- **Tools** — `read_attachment`, `call_agent` (delegate to another agent),
  `web_fetch`, `memory_store` / `memory_recall`, and MCP tools.
- **Workflows** — connect agents into a **graph** that runs in parallel with
  fan-out / fan-in / conditional branches (the upgrade over sequential pipelines).
- **Chat** — streaming chat with any agent (UI or REST).
- **Debug** — inspect messages, tool calls, token usage, latency.
- **Compactor** — summarize long sessions to fit the context window.

---

## Stack

| Layer | Choice |
|-------|--------|
| Backend | Python ≥ 3.11, FastAPI, SQLAlchemy 2.0 (async) + Alembic, SQLite→Postgres |
| LLM | `openai` SDK (OpenAI-compatible only) |
| MCP | `mcp` Python SDK (client) |
| Frontend | Next.js 15 (App Router), Tailwind, shadcn/ui, Zod, Zustand, TanStack Query |

---

## Structure

```
open-agent/
├── docs/                 # ARCHITECTURE, database-schema, api-reference, modules/*
├── backend/              # FastAPI: app/{db,models,schemas,repositories,services,core,api}
└── frontend/             # Next.js: app/, components/, lib/, stores/, hooks/, types/
```

Read `docs/ARCHITECTURE.md` for the big picture, `docs/database-schema.md` for
the DB, `docs/api-reference.md` for the REST surface, and `docs/modules/*` for
per-module design (especially `workflows.md`).

---

## Quick Start (dev)

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

---

## Scope (v1)

**In:** providers, models, agents, MCP, chat, debug, compactor, graph workflows.
**Out (for now):** multi-user RBAC, channel adapters (Telegram/Discord/...),
P2P networking, WASM sandbox. Add later as needed.

MIT.
