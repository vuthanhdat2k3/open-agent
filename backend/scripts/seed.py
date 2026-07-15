import asyncio
import os

from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models.agent import Agent
from app.models.model import Model
from app.models.provider import Provider
from app.models.mcp import McpServer, McpTool
from app.models.workflow import Workflow
from app.models.session import Session
from app.models.message import Message
from app.models.usage import UsageEvent


# --- idempotent helpers (skip if a row with the same unique key exists) ---


async def _provider(db, name, **kwargs):
    row = (await db.execute(select(Provider).where(Provider.name == name))).scalars().first()
    if row:
        return row
    row = Provider(name=name, **kwargs)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def _model(db, provider_id, name, **kwargs):
    row = (
        await db.execute(
            select(Model).where(Model.provider_id == provider_id, Model.name == name)
        )
    ).scalars().first()
    if row:
        return row
    row = Model(provider_id=provider_id, name=name, **kwargs)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def _model_by_name(db, name):
    return (await db.execute(select(Model).where(Model.name == name))).scalars().first()


async def _agent(db, name, **kwargs):
    row = (await db.execute(select(Agent).where(Agent.name == name))).scalars().first()
    if row:
        return row
    row = Agent(name=name, **kwargs)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def _mcp(db, name, tools, **kwargs):
    row = (await db.execute(select(McpServer).where(McpServer.name == name))).scalars().first()
    if row:
        return row
    row = McpServer(name=name, **kwargs)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    for t in tools:
        db.add(
            McpTool(
                server_id=row.id,
                name=t["name"],
                description=t.get("description", ""),
                input_schema=t.get("input_schema", {}),
            )
        )
    await db.commit()
    return row


async def _workflow(db, name, graph, **kwargs):
    row = (await db.execute(select(Workflow).where(Workflow.name == name))).scalars().first()
    if row:
        return row
    row = Workflow(name=name, graph=graph, **kwargs)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def _session(db, title, agent_id, messages):
    row = (await db.execute(select(Session).where(Session.title == title))).scalars().first()
    if row:
        return row
    row = Session(agent_id=agent_id, title=title)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    for i, m in enumerate(messages):
        db.add(Message(session_id=row.id, position=i, **m))
    await db.commit()
    return row


async def _usage(db, rows):
    # Usage rows have no natural unique key, so seed only while the table is
    # sparse. Re-running tops it up to a stable size instead of piling up.
    count = (await db.execute(select(func.count()).select_from(UsageEvent))).scalar_one()
    if count >= 5:
        return
    for r in rows:
        db.add(UsageEvent(**r))
    await db.commit()


async def seed() -> None:
    async with SessionLocal() as db:
        # --- Providers ---
        openai = await _provider(
            db,
            "OpenAI",
            key="openai",
            base_url=os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            api_key=os.environ.get("OPENAI_API_KEY", ""),
            env_var="OpenAI-API-KEY",
            is_default=True,
        )
        anthropic = await _provider(
            db,
            "Anthropic",
            key="anthropic",
            base_url="https://api.anthropic.com/v1",
            api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
            env_var="Anthropic-API-KEY",
            is_default=False,
        )
        ollama = await _provider(
            db,
            "Ollama",
            key="ollama",
            base_url="http://localhost:11434/v1",
            api_key=os.environ.get("OLLAMA_API_KEY", ""),
            env_var="Ollama-API-KEY",
            is_default=False,
        )

        # --- Models ---
        await _model(
            db,
            openai.id,
            "gpt-4o-mini",
            display_name="GPT-4o mini",
            tier="balanced",
            context_window=128000,
            input_cost_per_1k=0.00015,
            output_cost_per_1k=0.0006,
            active=True,
        )
        await _model(
            db,
            openai.id,
            "gpt-4o",
            display_name="GPT-4o",
            tier="frontier",
            context_window=128000,
            input_cost_per_1k=0.0005,
            output_cost_per_1k=0.0015,
            active=True,
        )
        claude_sonnet = await _model(
            db,
            anthropic.id,
            "claude-3-5-sonnet",
            display_name="Claude 3.5 Sonnet",
            tier="frontier",
            context_window=200000,
            input_cost_per_1k=0.0003,
            output_cost_per_1k=0.0015,
            active=True,
        )
        await _model(
            db,
            anthropic.id,
            "claude-3-haiku",
            display_name="Claude 3 Haiku",
            tier="economy",
            context_window=200000,
            input_cost_per_1k=0.000025,
            output_cost_per_1k=0.000125,
            active=True,
        )
        await _model(
            db,
            ollama.id,
            "llama3.1",
            display_name="Llama 3.1 8B",
            tier="balanced",
            context_window=131072,
            input_cost_per_1k=0.0,
            output_cost_per_1k=0.0,
            active=True,
        )
        await _model(
            db,
            ollama.id,
            "qwen2.5",
            display_name="Qwen 2.5 7B",
            tier="economy",
            context_window=32768,
            input_cost_per_1k=0.0,
            output_cost_per_1k=0.0,
            active=True,
        )

        # --- Agents ---
        await _agent(
            db,
            "general",
            description="General-purpose assistant",
            system_prompt=(
                "You are a helpful assistant. Use the provided tools when they "
                "help accomplish the user's request."
            ),
            model_id=(await _model_by_name(db, "gpt-4o-mini")).id,
            tools=[
                "read_attachment",
                "web_fetch",
                "memory_store",
                "memory_recall",
                "call_agent",
            ],
            max_iterations=12,
            temperature=0.7,
        )
        researcher = await _agent(
            db,
            "researcher",
            description="Deep web research and synthesis",
            system_prompt=(
                "You are a research agent. Break the question into sub-questions, "
                "fetch authoritative sources, and synthesize a cited answer."
            ),
            model_id=claude_sonnet.id,
            tools=["web_fetch", "memory_store", "memory_recall", "read_attachment"],
            max_iterations=20,
            temperature=0.3,
        )
        coder = await _agent(
            db,
            "coder",
            description="Code generation and file edits",
            system_prompt=(
                "You are a coding agent. Read the relevant files, plan the change, "
                "and implement it with clear, minimal diffs."
            ),
            model_id=(await _model_by_name(db, "gpt-4o")).id,
            tools=["read_attachment", "memory_store", "memory_recall"],
            max_iterations=16,
            temperature=0.2,
        )
        summarizer = await _agent(
            db,
            "summarizer",
            description="Concise summarization",
            system_prompt=(
                "You are a summarization agent. Produce a tight, structured summary "
                "that preserves the key facts and omits filler."
            ),
            model_id=(await _model_by_name(db, "claude-3-haiku")).id,
            tools=["read_attachment", "memory_store"],
            max_iterations=8,
            temperature=0.4,
        )

        # --- MCP servers + tools ---
        await _mcp(
            db,
            "filesystem",
            tools=[
                {"name": "read_file", "description": "Read a file from disk"},
                {"name": "write_file", "description": "Write a file to disk"},
                {"name": "list_dir", "description": "List a directory's contents"},
            ],
            transport="stdio",
            command="npx",
            args=["-y", "@modelcontextprotocol/server-filesystem", "/data"],
        )
        await _mcp(
            db,
            "fetch",
            tools=[{"name": "fetch", "description": "Fetch a URL and return its text"}],
            transport="stdio",
            command="uvx",
            args=["mcp-server-fetch"],
        )

        # --- Workflows (graph DAGs) ---
        await _workflow(
            db,
            "research-pipeline",
            graph={
                "nodes": [
                    {"id": "in", "kind": "input", "label": "input", "config": {}},
                    {
                        "id": "r",
                        "kind": "agent",
                        "label": "researcher",
                        "agent_id": researcher.id,
                        "config": {},
                    },
                    {
                        "id": "s",
                        "kind": "agent",
                        "label": "summarizer",
                        "agent_id": summarizer.id,
                        "config": {},
                    },
                    {"id": "out", "kind": "output", "label": "output", "config": {}},
                ],
                "edges": [
                    {"from_": "in", "to": "r"},
                    {"from_": "r", "to": "s"},
                    {"from_": "s", "to": "out"},
                ],
            },
            description="Research a topic, then summarize the findings",
        )
        await _workflow(
            db,
            "doc-summary",
            graph={
                "nodes": [
                    {"id": "in", "kind": "input", "label": "input", "config": {}},
                    {
                        "id": "s",
                        "kind": "agent",
                        "label": "summarizer",
                        "agent_id": summarizer.id,
                        "config": {},
                    },
                    {"id": "out", "kind": "output", "label": "output", "config": {}},
                ],
                "edges": [
                    {"from_": "in", "to": "s"},
                    {"from_": "s", "to": "out"},
                ],
            },
            description="Summarize an uploaded document",
        )

        # --- Sessions + messages ---
        await _session(
            db,
            "Demo chat with researcher",
            researcher.id,
            [
                {"role": "user", "content": "What are the trade-offs of SQLite vs Postgres for a small app?"},
                {
                    "role": "assistant",
                    "content": "SQLite is serverless and zero-config... Postgres adds concurrency and richer types. For a single-user app, SQLite is usually enough.",
                    "meta": {"model": "claude-3-5-sonnet", "input_tokens": 18, "output_tokens": 42},
                },
            ],
        )
        await _session(
            db,
            "Demo chat with coder",
            coder.id,
            [
                {"role": "user", "content": "Write a Python function to flatten a nested list."},
                {
                    "role": "assistant",
                    "content": "def flatten(xs):\n    for x in xs:\n        if isinstance(x, list):\n            yield from flatten(x)\n        else:\n            yield x",
                    "meta": {"model": "gpt-4o", "input_tokens": 12, "output_tokens": 55},
                },
            ],
        )

        # --- Usage analytics (only when empty) ---
        await _usage(
            db,
            [
                {"source": "chat", "agent_name": "researcher", "model_name": "claude-3-5-sonnet", "input_tokens": 1820, "output_tokens": 940, "cost_usd": 0.0123, "latency_ms": 4200},
                {"source": "chat", "agent_name": "coder", "model_name": "gpt-4o", "input_tokens": 1210, "output_tokens": 760, "cost_usd": 0.0091, "latency_ms": 3100},
                {"source": "call_agent", "agent_name": "summarizer", "model_name": "claude-3-haiku", "input_tokens": 540, "output_tokens": 210, "cost_usd": 0.0008, "latency_ms": 900},
                {"source": "workflow", "agent_name": "research-pipeline", "model_name": "claude-3-5-sonnet", "input_tokens": 4200, "output_tokens": 1800, "cost_usd": 0.031, "latency_ms": 9800},
                {"source": "completion", "agent_name": "general", "model_name": "gpt-4o-mini", "input_tokens": 320, "output_tokens": 88, "cost_usd": 0.0009, "latency_ms": 700},
            ],
        )


if __name__ == "__main__":
    asyncio.run(seed())
