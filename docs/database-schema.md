# OpenAgent — Database Schema

SQLAlchemy 2.0 (async) ORM, managed by Alembic. SQLite for dev; Postgres-ready
(swap `OPENAGENT_DB_URL`, use `asyncpg`). All timestamps are UTC `datetime`.
All primary keys are UUID strings (generated in app code) for portability.

---

## 1. Entity Relationship Overview

```
Provider (1) ──< Model (*)
Agent (*) ──── uses ──> Model (1)
Agent (*) ──── has ───> ToolGrant (*)            # granted tool ids (builtin + mcp)
McpServer (1) ──< McpTool (*)
Workflow (1) ──< WorkflowNode (*)               # node = agent | tool | input | merge | output
Workflow (1) ──< WorkflowEdge (*)               # edge = dependency / data flow
Session (1) ──< Message (*)                     # chat history for an agent
UsageEvent (*)                                   # token/cost log per call
```

---

## 2. Tables

### 2.1 `providers`
OpenAI-compatible LLM endpoints. Secrets are **never** stored — only the env-var
name that holds the key.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | String(36) | PK | UUID |
| `name` | String(128) | NOT NULL, UNIQUE | "openai", "groq"… |
| `base_url` | String(512) | NOT NULL | `https://api.openai.com/v1` |
| `api_key_env` | String(128) | NOT NULL | env var name (e.g. `OPENAI_API_KEY`) |
| `is_default` | Boolean | default False | seeded default |
| `created_at` | DateTime | NOT NULL | UTC |
| `updated_at` | DateTime | NOT NULL | UTC |

Indexes: `uq_providers_name`, `ix_providers_is_default`.

### 2.2 `models`
Models attached to a provider, with cost/tier metadata for metering.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | String(36) | PK | UUID |
| `provider_id` | String(36) | FK → providers.id, NOT NULL | |
| `name` | String(128) | NOT NULL | API model id, e.g. `gpt-4o-mini` |
| `display_name` | String(128) | NOT NULL | human label |
| `tier` | String(32) | NOT NULL | `frontier|smart|balanced|fast` |
| `context_window` | Integer | NOT NULL | tokens |
| `input_cost_per_1k` | Float | default 0.0 | USD per 1k input tokens |
| `output_cost_per_1k` | Float | default 0.0 | USD per 1k output tokens |
| `active` | Boolean | default True | shown in picker |
| `created_at` | DateTime | NOT NULL | |

Indexes: `uq_models_provider_name (provider_id, name)`, `ix_models_active`.
Unique per provider+name.

### 2.3 `agents`
Configured agents (system prompt + model + granted tools).

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | String(36) | PK | UUID |
| `name` | String(128) | NOT NULL, UNIQUE | |
| `description` | String(512) | | |
| `system_prompt` | Text | NOT NULL | |
| `model_id` | String(36) | FK → models.id, NOT NULL | |
| `tools` | Text(JSON) | NOT NULL | `["read_attachment","call_agent","web_fetch","memory_store","mcp:srv:t"]` |
| `max_iterations` | Integer | default 12 | loop cap |
| `temperature` | Float | default 0.7 | |
| `created_at` | DateTime | NOT NULL | |
| `updated_at` | DateTime | NOT NULL | |

Note: `tools` is a JSON list of granted tool ids. The agent only sees those.

### 2.4 `mcp_servers`
Registered MCP servers.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | String(36) | PK | UUID |
| `name` | String(128) | NOT NULL, UNIQUE | |
| `transport` | String(32) | NOT NULL | `stdio|sse|http` |
| `command` | String(512) | | for stdio (e.g. `npx`) |
| `args` | Text(JSON) | | stdio args (list) |
| `url` | String(512) | | for sse/http |
| `env` | Text(JSON) | | env vars (names only; values from env at runtime) |
| `enabled` | Boolean | default True | |
| `connected` | Boolean | default False | last-known connection state |
| `created_at` | DateTime | NOT NULL | |

### 2.5 `mcp_tools`
Tools discovered on a connected MCP server.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | String(36) | PK | UUID |
| `server_id` | String(36) | FK → mcp_servers.id, NOT NULL | |
| `tool_name` | String(256) | NOT NULL | remote tool name |
| `description` | Text | | |
| `input_schema` | Text(JSON) | | JSON schema of arguments |
| `granted` | Boolean | default True | show in agent tool picker |

Unique: `(server_id, tool_name)`. Index: `ix_mcp_tools_server`.

### 2.6 `workflows`
A multi-agent graph.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | String(36) | PK | UUID |
| `name` | String(128) | NOT NULL, UNIQUE | |
| `description` | String(512) | | |
| `graph` | Text(JSON) | NOT NULL | `{ "nodes": [...], "edges": [...] }` (see workflows.md) |
| `entry_node_id` | String(36) | | first node to run |
| `created_at` | DateTime | NOT NULL | |
| `updated_at` | DateTime | NOT NULL | |

### 2.7 `sessions`
Chat sessions (one agent per session in v1).

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | String(36) | PK | UUID |
| `agent_id` | String(36) | FK → agents.id, NOT NULL | |
| `title` | String(256) | | |
| `status` | String(32) | default `active` | `active|archived` |
| `created_at` | DateTime | NOT NULL | |
| `updated_at` | DateTime | NOT NULL | |

Index: `ix_sessions_agent`, `ix_sessions_updated`.

### 2.8 `messages`
Conversation history. Block-based to support tool calls & images.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | String(36) | PK | UUID |
| `session_id` | String(36) | FK → sessions.id, NOT NULL | |
| `role` | String(32) | NOT NULL | `system|user|assistant|tool` |
| `content` | Text | | text body |
| `tool_calls` | Text(JSON) | | assistant: list of `{id,name,args}` |
| `tool_call_id` | String(128) | | tool result: links to a tool_call id |
| `meta` | Text(JSON) | | `{model, in_tokens, out_tokens, cost_usd, latency_ms, compacted}` |
| `seq` | Integer | NOT NULL | ordering within session |
| `created_at` | DateTime | NOT NULL | |

Indexes: `ix_messages_session_seq`, `ix_messages_session`.
Note: `content` holds text; for multimodal, `meta` may carry refs (v1 text-only).

### 2.9 `usage_events`
Metering / cost log.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | String(36) | PK | UUID |
| `agent_id` | String(36) | | nullable (workflow nodes too) |
| `workflow_id` | String(36) | | nullable |
| `model_id` | String(36) | | |
| `session_id` | String(36) | | |
| `in_tokens` | Integer | default 0 | |
| `out_tokens` | Integer | default 0 | |
| `cost_usd` | Float | default 0.0 | |
| `created_at` | DateTime | NOT NULL | |

Indexes: `ix_usage_agent`, `ix_usage_created`, `ix_usage_workflow`.

---

## 3. SQLAlchemy Model Sketch (`app/models/`)

```python
from sqlalchemy import String, Boolean, Integer, Float, Text, DateTime, ForeignKey
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
import datetime, uuid

class Base(DeclarativeBase): pass

def _pk() -> str: return str(uuid.uuid4())
def _now() -> datetime.datetime: return datetime.datetime.now(datetime.timezone.utc)

class Provider(Base):
    __tablename__ = "providers"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_pk)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    base_url: Mapped[str] = mapped_column(String(512), nullable=False)
    api_key_env: Mapped[str] = mapped_column(String(128), nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=_now, onupdate=_now)
    models: Mapped[list["Model"]] = relationship(back_populates="provider")

class Model(Base):
    __tablename__ = "models"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_pk)
    provider_id: Mapped[str] = mapped_column(ForeignKey("providers.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    tier: Mapped[str] = mapped_column(String(32), nullable=False)
    context_window: Mapped[int] = mapped_column(Integer, nullable=False)
    input_cost_per_1k: Mapped[float] = mapped_column(Float, default=0.0)
    output_cost_per_1k: Mapped[float] = mapped_column(Float, default=0.0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=_now)
    provider: Mapped["Provider"] = relationship(back_populates="models")
    __table_args__ = (UniqueConstraint("provider_id", "name", name="uq_models_provider_name"),)
```

(Other entities follow the same shape; full definitions live in `app/models/`.)

---

## 4. Migration Strategy

- **Dev**: Alembic `upgrade head` on startup (idempotent).
- **Initial migration** creates all tables above.
- **Adding a column**: new Alembic revision; never edit old migrations.
- **Seeds**: `scripts/seed.py` inserts a default `Provider` + `Model` from env
  (`OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_DEFAULT_MODEL`) if none exist.

---

## 5. Sizing Notes

- SQLite handles a personal workload easily (single writer). For concurrent
  multi-user later, switch to Postgres (`postgresql+asyncpg://…`).
- `messages.content`/`tool_calls`/`meta` are JSON text; consider
  `JSONB`/native JSON column on Postgres for queryability.
- Add `ix_messages_session_seq` so chat reload + compaction are O(log n).
