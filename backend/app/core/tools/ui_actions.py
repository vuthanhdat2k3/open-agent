"""Client Tool Bridge tools: control the browser UI the user has open.

Unlike every other tool in this package, ``run()`` here does no work itself —
it emits a ``ui_action`` progress event (picked up by the Companion Operator
in the browser over the existing chat SSE stream), then blocks on
``ui_bridge.wait_for_result`` until the browser executes the action and posts
a result back. See ``docs/companion-operator-agent-v2-spec.md`` for the full
protocol and guardrail rationale.

Naming: existing tools in this package are flat snake_case (``workflow_list``,
``web_search``); these follow the same convention (``ui_navigate``, not
``ui.navigate``) for consistency, even though the design doc used dotted
names as a category label.
"""

from __future__ import annotations

import uuid
from typing import Any

from app.core.tools.registry import register
from app.core.tools.risk_tier import RiskTier
from app.core.tools.types import ToolContext, ToolSpec
from app.core.tools.ui_bridge import wait_for_result

# How long a ui_* tool waits for the browser to act before giving the agent a
# structured timeout instead of hanging the run. The user may be mid-action
# (typing, scrolling) — generous, but bounded well under the agent loop's own
# per-tool ceiling.
_DEFAULT_TIMEOUT_S = 20.0


async def _dispatch(ctx: ToolContext, tool: str, args: dict[str, Any], timeout_s: float = _DEFAULT_TIMEOUT_S) -> str:
    """Emit a ui_action event and wait for the browser's result.

    Every ui_* tool shares this shape: no ui_action needs a distinct
    execution path, only distinct arguments.
    """
    call_id = uuid.uuid4().hex
    if ctx.emit:
        await ctx.emit(
            {
                "type": "ui_action",
                "call_id": call_id,
                "tool": tool,
                "args": args,
                "timeout_ms": int(timeout_s * 1000),
            }
        )
    result = await wait_for_result(call_id, timeout_s)
    if not result.get("ok"):
        return f"error: {result.get('error') or 'ui action failed'}"
    import json

    return json.dumps(result.get("result") or {}, ensure_ascii=False)


async def _ui_read_screen(args: dict[str, Any], ctx: ToolContext) -> str:
    return await _dispatch(ctx, "ui_read_screen", {})


register(
    ToolSpec(
        name="ui_read_screen",
        description=(
            "Read what the user currently has open in the app: route, page title, "
            "active filters, the currently selected item, and the ids/labels of "
            "items visible on screen. Use this before acting on 'this', 'the one "
            "I have open', or similar references to the user's current screen."
        ),
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        risk_tier=RiskTier.safe,
        timeout_s=_DEFAULT_TIMEOUT_S + 5,
        run=_ui_read_screen,
    )
)


async def _ui_navigate(args: dict[str, Any], ctx: ToolContext) -> str:
    route = str(args.get("route") or "").strip()
    if not route:
        return "error: 'route' is required"
    return await _dispatch(ctx, "ui_navigate", {"route": route, "params": args.get("params") or {}})


register(
    ToolSpec(
        name="ui_navigate",
        description=(
            "Navigate the user's browser to a page in this app, e.g. '/reports' or "
            "'/workflows'. Only pages already registered in the app's navigation "
            "are reachable; an unregistered route returns an error instead of "
            "navigating."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "route": {"type": "string", "description": "App-relative path, e.g. '/reports'."},
                "params": {"type": "object", "description": "Optional query params to apply after navigating."},
            },
            "required": ["route"],
            "additionalProperties": False,
        },
        risk_tier=RiskTier.safe,
        timeout_s=_DEFAULT_TIMEOUT_S + 5,
        run=_ui_navigate,
    )
)


async def _ui_set_filter(args: dict[str, Any], ctx: ToolContext) -> str:
    filters = args.get("filters")
    if not isinstance(filters, dict) or not filters:
        return "error: 'filters' must be a non-empty object"
    return await _dispatch(ctx, "ui_set_filter", {"filters": filters})


register(
    ToolSpec(
        name="ui_set_filter",
        description=(
            "Apply filters on the page the user currently has open (e.g. status, "
            "date range). Only filters the current page has registered are "
            "accepted — call ui_read_screen first if unsure what is available."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "filters": {"type": "object", "description": "Filter key/value pairs for the current page."},
            },
            "required": ["filters"],
            "additionalProperties": False,
        },
        risk_tier=RiskTier.safe,
        timeout_s=_DEFAULT_TIMEOUT_S + 5,
        run=_ui_set_filter,
    )
)


async def _ui_open_panel(args: dict[str, Any], ctx: ToolContext) -> str:
    panel = str(args.get("panel") or "").strip()
    if not panel:
        return "error: 'panel' is required"
    return await _dispatch(ctx, "ui_open_panel", {"panel": panel, "id": args.get("id")})


register(
    ToolSpec(
        name="ui_open_panel",
        description=(
            "Open a dialog or side panel already registered on the user's current "
            "page (e.g. a run's detail view). Call ui_read_screen first to see "
            "which panels the current page exposes."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "panel": {"type": "string", "description": "Registered panel name for the current page."},
                "id": {"type": "string", "description": "Optional record id the panel should open for."},
            },
            "required": ["panel"],
            "additionalProperties": False,
        },
        risk_tier=RiskTier.safe,
        timeout_s=_DEFAULT_TIMEOUT_S + 5,
        run=_ui_open_panel,
    )
)


async def _ui_fill_form(args: dict[str, Any], ctx: ToolContext) -> str:
    form = str(args.get("form") or "").strip()
    values = args.get("values")
    if not form:
        return "error: 'form' is required"
    if not isinstance(values, dict) or not values:
        return "error: 'values' must be a non-empty object"
    return await _dispatch(ctx, "ui_fill_form", {"form": form, "values": values})


register(
    ToolSpec(
        name="ui_fill_form",
        description=(
            "Fill fields of a form on the user's current page. This only fills "
            "the form for the user to review — it never submits it. Use "
            "ui_submit_form (which requires human approval) to actually submit."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "form": {"type": "string", "description": "Registered form name for the current page."},
                "values": {"type": "object", "description": "Field name/value pairs to fill."},
            },
            "required": ["form", "values"],
            "additionalProperties": False,
        },
        risk_tier=RiskTier.write,
        timeout_s=_DEFAULT_TIMEOUT_S + 5,
        run=_ui_fill_form,
    )
)


async def _ui_submit_form(args: dict[str, Any], ctx: ToolContext) -> str:
    form = str(args.get("form") or "").strip()
    if not form:
        return "error: 'form' is required"
    return await _dispatch(ctx, "ui_submit_form", {"form": form, "values": args.get("values") or {}})


register(
    ToolSpec(
        name="ui_submit_form",
        description=(
            "Submit a form on the user's current page — a real write action "
            "(e.g. creating a record). Requires human approval before it runs."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "form": {"type": "string", "description": "Registered form name for the current page."},
                "values": {"type": "object", "description": "Final field values to submit."},
            },
            "required": ["form"],
            "additionalProperties": False,
        },
        risk_tier=RiskTier.write,
        requires_approval=True,
        timeout_s=_DEFAULT_TIMEOUT_S + 5,
        run=_ui_submit_form,
    )
)
