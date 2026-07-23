import asyncio
import os

from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models.agent import Agent
from app.models.mcp import McpServer, McpTool
from app.models.membership import Membership
from app.models.message import Message
from app.models.model import Model
from app.models.organization import Organization
from app.models.provider import Provider
from app.models.role import Role
from app.models.session import Session
from app.models.usage import UsageEvent
from app.models.user import User
from app.models.workflow import Workflow

DEFAULT_ORG_ID = "default-org-id"
DEFAULT_USER_ID = "default-user-id"


async def _default_org_and_user(db):
    org = (
        (await db.execute(select(Organization).where(Organization.id == DEFAULT_ORG_ID)))
        .scalars()
        .first()
    )
    if not org:
        org = Organization(id=DEFAULT_ORG_ID, name="Default Organization", slug="default")
        db.add(org)
        await db.commit()
        await db.refresh(org)

    user = (await db.execute(select(User).where(User.id == DEFAULT_USER_ID))).scalars().first()
    if not user:
        user = User(
            id=DEFAULT_USER_ID, email="admin@openagent.local", display_name="Admin", is_active=True
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

    membership = (
        (
            await db.execute(
                select(Membership).where(Membership.org_id == org.id, Membership.user_id == user.id)
            )
        )
        .scalars()
        .first()
    )
    if not membership:
        membership = Membership(org_id=org.id, user_id=user.id, role=Role.owner)
        db.add(membership)
        await db.commit()

    return org, user


async def _provider(db, org_id, user_id, name, **kwargs):
    row = (
        (await db.execute(select(Provider).where(Provider.org_id == org_id, Provider.name == name)))
        .scalars()
        .first()
    )
    if row:
        return row
    row = Provider(org_id=org_id, created_by_user_id=user_id, name=name, **kwargs)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def _model(db, org_id, user_id, provider_id, name, **kwargs):
    row = (
        (
            await db.execute(
                select(Model).where(
                    Model.org_id == org_id, Model.provider_id == provider_id, Model.name == name
                )
            )
        )
        .scalars()
        .first()
    )
    if row:
        return row
    row = Model(
        org_id=org_id, created_by_user_id=user_id, provider_id=provider_id, name=name, **kwargs
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def _model_by_name(db, org_id, name):
    return (
        (await db.execute(select(Model).where(Model.org_id == org_id, Model.name == name)))
        .scalars()
        .first()
    )


async def _agent(db, org_id, user_id, name, **kwargs):
    row = (
        (await db.execute(select(Agent).where(Agent.org_id == org_id, Agent.name == name)))
        .scalars()
        .first()
    )
    if row:
        return row
    row = Agent(org_id=org_id, created_by_user_id=user_id, name=name, **kwargs)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def _mcp(db, org_id, user_id, name, tools, **kwargs):
    row = (
        (
            await db.execute(
                select(McpServer).where(McpServer.org_id == org_id, McpServer.name == name)
            )
        )
        .scalars()
        .first()
    )
    if row:
        return row
    row = McpServer(org_id=org_id, created_by_user_id=user_id, name=name, **kwargs)
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


async def _workflow(db, org_id, user_id, name, graph, **kwargs):
    row = (
        (await db.execute(select(Workflow).where(Workflow.org_id == org_id, Workflow.name == name)))
        .scalars()
        .first()
    )
    if row:
        return row
    row = Workflow(org_id=org_id, created_by_user_id=user_id, name=name, graph=graph, **kwargs)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def _session(db, org_id, user_id, title, agent_id, messages):
    row = (
        (await db.execute(select(Session).where(Session.org_id == org_id, Session.title == title)))
        .scalars()
        .first()
    )
    if row:
        return row
    row = Session(org_id=org_id, created_by_user_id=user_id, agent_id=agent_id, title=title)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    for i, m in enumerate(messages):
        db.add(
            Message(org_id=org_id, created_by_user_id=user_id, session_id=row.id, position=i, **m)
        )
    await db.commit()
    return row


async def _usage(db, org_id, user_id, rows):
    count = (
        await db.execute(
            select(func.count()).select_from(UsageEvent).where(UsageEvent.org_id == org_id)
        )
    ).scalar_one()
    if count >= 5:
        return
    for r in rows:
        db.add(UsageEvent(org_id=org_id, created_by_user_id=user_id, **r))
    await db.commit()


async def seed() -> None:
    async with SessionLocal() as db:
        org, user = await _default_org_and_user(db)
        org_id = org.id
        user_id = user.id

        # --- Providers ---
        openai = await _provider(
            db,
            org_id,
            user_id,
            "OpenAI",
            key="openai",
            base_url=os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            api_key=os.environ.get("OPENAI_API_KEY", ""),
            env_var="OpenAI-API-KEY",
            is_default=True,
        )
        anthropic = await _provider(
            db,
            org_id,
            user_id,
            "Anthropic",
            key="anthropic",
            base_url="https://api.anthropic.com/v1",
            api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
            env_var="Anthropic-API-KEY",
            is_default=False,
        )
        ollama = await _provider(
            db,
            org_id,
            user_id,
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
            org_id,
            user_id,
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
            org_id,
            user_id,
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
            org_id,
            user_id,
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
            org_id,
            user_id,
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
            org_id,
            user_id,
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
            org_id,
            user_id,
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
            org_id,
            user_id,
            "general",
            description="General-purpose assistant",
            system_prompt=(
                "You are a helpful assistant. Use the provided tools when they "
                "help accomplish the user's request."
            ),
            model_id=(await _model_by_name(db, org_id, "gpt-4o-mini")).id,
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
            org_id,
            user_id,
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
            org_id,
            user_id,
            "coder",
            description="Code generation and file edits",
            system_prompt=(
                "You are a coding agent. Read the relevant files, plan the change, "
                "and implement it with clear, minimal diffs."
            ),
            model_id=(await _model_by_name(db, org_id, "gpt-4o")).id,
            tools=["read_attachment", "memory_store", "memory_recall"],
            max_iterations=16,
            temperature=0.2,
        )
        summarizer = await _agent(
            db,
            org_id,
            user_id,
            "summarizer",
            description="Concise summarization",
            system_prompt=(
                "You are a summarization agent. Produce a tight, structured summary "
                "that preserves the key facts and omits filler."
            ),
            model_id=(await _model_by_name(db, org_id, "claude-3-haiku")).id,
            tools=["read_attachment", "memory_store"],
            max_iterations=8,
            temperature=0.4,
        )

        # --- MCP servers + tools ---
        await _mcp(
            db,
            org_id,
            user_id,
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
            org_id,
            user_id,
            "fetch",
            tools=[{"name": "fetch", "description": "Fetch a URL and return its text"}],
            transport="stdio",
            command="uvx",
            args=["mcp-server-fetch"],
        )

        # --- Workflows (graph DAGs) ---
        await _workflow(
            db,
            org_id,
            user_id,
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
            org_id,
            user_id,
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
            org_id,
            user_id,
            "Demo chat with researcher",
            researcher.id,
            [
                {
                    "role": "user",
                    "content": "What are the trade-offs of SQLite vs Postgres for a small app?",
                },
                {
                    "role": "assistant",
                    "content": "SQLite is serverless and zero-config... Postgres adds concurrency and richer types. For a single-user app, SQLite is usually enough.",
                    "meta": {"model": "claude-3-5-sonnet", "input_tokens": 18, "output_tokens": 42},
                },
            ],
        )
        await _session(
            db,
            org_id,
            user_id,
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
            org_id,
            user_id,
            [
                {
                    "source": "chat",
                    "agent_name": "researcher",
                    "model_name": "claude-3-5-sonnet",
                    "input_tokens": 1820,
                    "output_tokens": 940,
                    "cost_usd": 0.0123,
                    "latency_ms": 4200,
                },
                {
                    "source": "chat",
                    "agent_name": "coder",
                    "model_name": "gpt-4o",
                    "input_tokens": 1210,
                    "output_tokens": 760,
                    "cost_usd": 0.0091,
                    "latency_ms": 3100,
                },
                {
                    "source": "call_agent",
                    "agent_name": "summarizer",
                    "model_name": "claude-3-haiku",
                    "input_tokens": 540,
                    "output_tokens": 210,
                    "cost_usd": 0.0008,
                    "latency_ms": 900,
                },
                {
                    "source": "workflow",
                    "agent_name": "research-pipeline",
                    "model_name": "claude-3-5-sonnet",
                    "input_tokens": 4200,
                    "output_tokens": 1800,
                    "cost_usd": 0.031,
                    "latency_ms": 9800,
                },
                {
                    "source": "completion",
                    "agent_name": "general",
                    "model_name": "gpt-4o-mini",
                    "input_tokens": 320,
                    "output_tokens": 88,
                    "cost_usd": 0.0009,
                    "latency_ms": 700,
                },
            ],
        )


if __name__ == "__main__":
    asyncio.run(seed())
