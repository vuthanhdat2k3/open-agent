from datetime import timezone
from typing import Any

import httpx

from app.config import get_settings
from app.core.runtime_context import now_in_timezone

# Register the additional builtin tools (filesystem, shell, web search).
# Importing this module triggers their registration as a side effect.
from app.core.tools import (
    filesystem,  # noqa: F401
    memory,  # noqa: F401
    shell,  # noqa: F401
    web_search,  # noqa: F401
    youtube_search,  # noqa: F401
)
from app.core.tools.paths import safe_resolve, safe_url
from app.core.tools.registry import register
from app.core.tools.risk_tier import RiskTier
from app.core.tools.types import ToolContext, ToolSpec
from app.customer_intelligence.tools import register_customer_intelligence_tools  # noqa: F401

settings = get_settings()

# Fallback in-memory dictionary for testing/non-DB contexts
MEMORY: dict[str, str] = {}

MAX_ATTACHMENT_CHARS = 50_000


async def _get_current_time(args: dict[str, Any], ctx: ToolContext) -> str:
    del args
    current = now_in_timezone(ctx.timezone_name)
    return (
        f"UTC: {current.astimezone(timezone.utc).isoformat()}\n"
        f"Timezone: {ctx.timezone_name}\n"
        f"Local time: {current.isoformat()}\n"
        f"Local date: {current.strftime('%A, %Y-%m-%d')}"
    )


register(ToolSpec(
    name="get_current_time",
    description="Return the authoritative current UTC and local time for this run.",
    input_schema={"type": "object", "properties": {}, "additionalProperties": False},
    run=_get_current_time,
))


async def _read_attachment(args: dict[str, Any], ctx: ToolContext) -> str:
    path = args.get("path", "")
    if not path:
        return "error: missing 'path'"
    target = safe_resolve(ctx.workspace_dir, path)
    if target is None:
        return "error: path escapes workspace directory"
    if not target.is_file():
        return f"error: file not found: {path}"
    try:
        with open(target, encoding="utf-8", errors="replace") as f:
            data = f.read(MAX_ATTACHMENT_CHARS)
    except Exception as e:  # noqa: BLE001
        return f"error reading file: {e}"
    if len(data) == MAX_ATTACHMENT_CHARS:
        data += "\n...[truncated]"
    return data


MAX_FETCH_REDIRECTS = 5


async def _crawler_fetch(crawler_url: str, url: str, api_token: str = "") -> str | None:
    """POST to a self-hosted crawl4ai instance; returns rendered markdown or None on any failure."""
    headers = {"Authorization": f"Bearer {api_token}"} if api_token else {}
    async with httpx.AsyncClient(timeout=45.0) as client:
        resp = await client.post(f"{crawler_url.rstrip('/')}/crawl", json={"urls": [url]}, headers=headers)
        resp.raise_for_status()
        data = resp.json()
    results = data.get("results", data if isinstance(data, list) else [])
    if not results:
        return None
    result = results[0]
    if not result.get("success", True):
        return None
    markdown = result.get("markdown")
    # crawl4ai has returned either a plain string or a {"raw_markdown": ...,
    # "fit_markdown": ...} object across versions - handle both.
    if isinstance(markdown, dict):
        markdown = markdown.get("fit_markdown") or markdown.get("raw_markdown")
    return markdown or None


async def _web_fetch(args: dict[str, Any], ctx: ToolContext) -> str:
    url = args.get("url", "")
    if not url:
        return "error: missing 'url'"
    if safe_url(url) is None:
        return "error: url blocked (must be http/https and resolve to a public address)"

    fetch_settings = get_settings()
    crawler_url = fetch_settings.crawler_url
    if crawler_url:
        try:
            markdown = await _crawler_fetch(crawler_url, url, fetch_settings.crawler_api_token)
            if markdown:
                if len(markdown) > MAX_ATTACHMENT_CHARS:
                    markdown = markdown[:MAX_ATTACHMENT_CHARS] + "\n...[truncated]"
                return markdown
        except Exception:  # noqa: BLE001
            pass  # fall through to the plain fetch below

    try:
        # follow_redirects=False + manual hop validation: a redirect Location
        # is attacker-influenced same as the original URL, so each hop must
        # pass the same SSRF check before being followed (auto-follow would
        # let a safe URL redirect into an internal/metadata address).
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=False) as client:
            for _ in range(MAX_FETCH_REDIRECTS):
                resp = await client.get(url, headers={"User-Agent": "OpenAgent/0.1"})
                if resp.status_code in (301, 302, 303, 307, 308) and "location" in resp.headers:
                    next_url = str(httpx.URL(url).join(resp.headers["location"]))
                    if safe_url(next_url) is None:
                        return "error: url blocked (redirect target must be http/https and resolve to a public address)"
                    url = next_url
                    continue
                break
        text = resp.text
    except Exception as e:  # noqa: BLE001
        return f"error fetching url: {e}"
    if len(text) > MAX_ATTACHMENT_CHARS:
        text = text[:MAX_ATTACHMENT_CHARS] + "\n...[truncated]"
    return text


async def _memory_store(args: dict[str, Any], ctx: ToolContext) -> str:
    key = args.get("key")
    value = args.get("value", "")
    if not key:
        return "error: missing 'key'"
    if not ctx.db or not ctx.session_id:
        MEMORY[key] = str(value)
        return f"stored key '{key}'"

    from sqlalchemy import select

    from app.models.memory import SessionMemory

    db = ctx.db
    res = await db.execute(
        select(SessionMemory).where(
            SessionMemory.session_id == ctx.session_id, SessionMemory.key == key
        )
    )
    existing = res.scalar_one_or_none()
    if existing:
        existing.value = str(value)
    else:
        org_id = ctx.org_id
        if not org_id and ctx.session_id:
            from app.models.session import Session

            res_sess = await db.execute(select(Session.org_id).where(Session.id == ctx.session_id))
            org_id = res_sess.scalar_one_or_none()
        if not org_id:
            org_id = "default-org-id"

        db.add(
            SessionMemory(
                org_id=org_id,
                created_by_user_id=ctx.user_id,
                session_id=ctx.session_id,
                key=key,
                value=str(value),
            )
        )
    await db.commit()
    return f"stored key '{key}'"


async def _memory_recall(args: dict[str, Any], ctx: ToolContext) -> str:
    key = args.get("key")
    if not key:
        return "error: missing 'key'"
    if not ctx.db or not ctx.session_id:
        return MEMORY.get(key, "not found")

    from sqlalchemy import select

    from app.models.memory import SessionMemory

    db = ctx.db
    res = await db.execute(
        select(SessionMemory).where(
            SessionMemory.session_id == ctx.session_id, SessionMemory.key == key
        )
    )
    existing = res.scalar_one_or_none()
    if not existing:
        return "not found"
    return existing.value


async def _call_agent(args: dict[str, Any], ctx: ToolContext) -> str:
    target_agent_id = args.get("target_agent_id") or args.get("agent_id")
    instruction = args.get("instruction") or args.get("message") or ""
    if not target_agent_id:
        return "error: missing 'target_agent_id'"
    if not instruction:
        return "error: missing 'instruction'"
    from app.config import get_settings

    if ctx.depth >= get_settings().max_agent_depth:
        return f"error: max agent depth ({get_settings().max_agent_depth}) exceeded"
    # Lazy import to avoid circular dependency with agent_loop.
    from sqlalchemy import select

    from app.core.agent_loop import run_agent_loop
    from app.db.base import utc_now
    from app.models.agent import Agent
    from app.models.approval_request import ApprovalRequest
    from app.models.task import Task

    result = await ctx.db.execute(
        select(Agent).where(Agent.id == target_agent_id, Agent.org_id == ctx.org_id)
    )
    agent = result.scalar_one_or_none()
    if agent is None:
        return f"error: agent '{target_agent_id}' not found"

    task = Task(
        org_id=agent.org_id,
        parent_task_id=ctx.current_task_id,
        root_run_id=ctx.root_run_id or ctx.session_id or ctx.current_task_id or agent.id,
        agent_id=agent.id,
        agent_release_id=agent.active_release_id,
        goal=instruction,
        status="running",
        progress={"model_id": ctx.model_id},
        depth=ctx.depth + 1,
        started_at=utc_now(),
    )
    ctx.db.add(task)
    await ctx.db.commit()
    await ctx.db.refresh(task)

    try:
        loop_result = await run_agent_loop(
            agent,
            instruction,
            ctx.db,
            depth=ctx.depth + 1,
            current_task_id=task.id,
            root_run_id=task.root_run_id,
            user_id=ctx.user_id,
            model_id=ctx.model_id,
            timezone_name=ctx.timezone_name,
        )
    except Exception as exc:  # noqa: BLE001
        task.status = "failed"
        task.result = str(exc)
        task.finished_at = utc_now()
        await ctx.db.commit()
        return f"error: subagent failed: {exc}"

    pending = await ctx.db.execute(
        select(ApprovalRequest).where(
            ApprovalRequest.run_id == task.root_run_id,
            ApprovalRequest.org_id == agent.org_id,
            ApprovalRequest.status == "pending",
        ).limit(1)
    )
    approval = pending.scalar_one_or_none()
    if approval is not None:
        # The root run (agent_loop._agent_stream) is the one the UI resumes
        # via /api/approvals — it detects this same pending approval right
        # after this call returns and puts itself into waiting_approval.
        # This sub-task must NOT also claim waiting_approval: a decide-approval
        # resume re-runs the *root* run from its original message, it never
        # re-enters this delegated sub-task, so leaving it at waiting_approval
        # would strand it there forever (and previously made the approval
        # decision endpoint's `Task.status == "waiting_approval"` query
        # ambiguous between this row and the root task, resuming whichever
        # one the query happened to return first — often the wrong one).
        task.status = "succeeded"
        task.result = f"approval required for {approval.tool_name} (approval_id: {approval.id})"
        task.finished_at = utc_now()
        await ctx.db.commit()
        return f"approval required for {approval.tool_name} (approval_id: {approval.id})"

    task.status = "succeeded"
    task.result = loop_result.content
    task.token_usage = loop_result.usage
    task.finished_at = utc_now()
    await ctx.db.commit()
    return loop_result.content


register(
    ToolSpec(
        name="read_attachment",
        description="Read a text file from the workspace. Provide a relative 'path'.",
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative path inside workspace"}
            },
            "required": ["path"],
        },
        run=_read_attachment,
        risk_tier=RiskTier.read,
    )
)

register(
    ToolSpec(
        name="web_fetch",
        description="Fetch a URL and return its text content.",
        input_schema={
            "type": "object",
            "properties": {"url": {"type": "string", "description": "Full URL to fetch"}},
            "required": ["url"],
        },
        run=_web_fetch,
        risk_tier=RiskTier.network,
    )
)

register(
    ToolSpec(
        name="memory_store",
        description="Store a value under a key in the agent memory.",
        input_schema={
            "type": "object",
            "properties": {
                "key": {"type": "string"},
                "value": {"type": "string"},
            },
            "required": ["key", "value"],
        },
        run=_memory_store,
        risk_tier=RiskTier.safe,
    )
)

register(
    ToolSpec(
        name="memory_recall",
        description="Recall a previously stored value by key.",
        input_schema={
            "type": "object",
            "properties": {"key": {"type": "string"}},
            "required": ["key"],
        },
        run=_memory_recall,
        risk_tier=RiskTier.safe,
    )
)

register(
    ToolSpec(
        name="call_agent",
        description=(
            "Delegate a task to another configured agent by id. Returns that agent's final answer."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "target_agent_id": {"type": "string"},
                "instruction": {"type": "string"},
            },
            "required": ["target_agent_id", "instruction"],
        },
        run=_call_agent,
        risk_tier=RiskTier.execute,
    )
)


async def _call_external_agent(args: dict[str, Any], ctx: ToolContext) -> str:
    endpoint_url = args.get("endpoint_url", "")
    target_agent_id = args.get("agent_id")
    task_input = args.get("input", "")

    if not endpoint_url or not task_input:
        return "error: missing 'endpoint_url' or 'input'"

    if safe_url(endpoint_url) is None:
        return "error: url blocked (must be http/https and resolve to a public address)"

    token = "a2a_token"
    if ctx.db and ctx.org_id and ctx.agent_id and ctx.user_id:
        from sqlalchemy import select

        from app.core.auth.token_exchange import exchange_token_for_agent
        from app.models.agent_identity import AgentIdentity

        stmt = select(AgentIdentity).where(
            AgentIdentity.org_id == ctx.org_id,
            AgentIdentity.agent_id == ctx.agent_id,
        )
        res = await ctx.db.execute(stmt)
        identity = res.scalar_one_or_none()
        if not identity or not identity.enabled:
            return "error: agent identity not configured or disabled for external A2A"

        try:
            token = exchange_token_for_agent(
                user_id=ctx.user_id,
                org_id=ctx.org_id,
                agent_identity=identity,
                target_audience=endpoint_url,
            )
        except ValueError as exc:
            return f"error: token exchange denied: {exc}"

    try:
        from app.a2a.client import call_external_agent_endpoint
        result = await call_external_agent_endpoint(
            endpoint_url=endpoint_url,
            token=token,
            task_input=task_input,
            agent_id=target_agent_id,
        )
        return result
    except Exception as e:  # noqa: BLE001
        return f"error calling external agent: {e}"


register(
    ToolSpec(
        name="call_external_agent",
        description="Call an external agent exposed via A2A protocol or task endpoint URL.",
        input_schema={
            "type": "object",
            "properties": {
                "endpoint_url": {"type": "string", "description": "A2A task endpoint URL"},
                "agent_id": {"type": "string", "description": "Optional target agent ID"},
                "input": {"type": "string", "description": "Task input prompt"},
            },
            "required": ["endpoint_url", "input"],
        },
        run=_call_external_agent,
        risk_tier=RiskTier.network,
    )
)

