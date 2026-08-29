from __future__ import annotations

import json
from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.exc import IntegrityError

from app.core.authz.scope import scope_to_owner
from app.core.tools.registry import register
from app.core.tools.risk_tier import RiskTier
from app.core.tools.types import ToolContext, ToolSpec
from app.db.base import gen_id
from app.models.workflow import Workflow
from app.models.workflow_installation import WorkflowInstallation
from app.models.workflow_template import WorkflowTemplate, WorkflowTemplateVersion
from app.schemas.workflow import WorkflowValidationError
from app.services.workflow_service import WorkflowService


# ---------------------------------------------------------------------------
# 1. workflow_list: List all available workflows in workspace
# ---------------------------------------------------------------------------
async def _workflow_list(args: dict[str, Any], ctx: ToolContext) -> str:
    """List workflows owned by the current user or available in the organization."""
    query = (args.get("query") or "").strip().lower()
    limit = min(int(args.get("limit") or 50), 100)

    stmt = select(Workflow).where(Workflow.org_id == ctx.org_id)
    if ctx.user_id:
        stmt = scope_to_owner(stmt, ctx.db, Workflow.created_by_user_id)

    res = await ctx.db.execute(stmt.order_by(Workflow.created_at.desc()).limit(limit))
    workflows = res.scalars().all()

    if query:
        workflows = [
            w
            for w in workflows
            if query in w.name.lower() or query in (w.description or "").lower()
        ]

    if not workflows:
        return json.dumps(
            {
                "workflows": [],
                "count": 0,
                "message": "No workflows found in this workspace.",
            },
            ensure_ascii=False,
            indent=2,
        )

    items = []
    for w in workflows:
        graph = w.graph or {}
        nodes = graph.get("nodes") or []
        items.append(
            {
                "id": w.id,
                "name": w.name,
                "description": w.description or "",
                "node_count": len(nodes),
                "created_at": w.created_at.isoformat() if w.created_at else None,
                "updated_at": w.updated_at.isoformat() if w.updated_at else None,
            }
        )

    return json.dumps(
        {"workflows": items, "count": len(items)}, ensure_ascii=False, indent=2
    )


register(
    ToolSpec(
        name="workflow_list",
        description=(
            "List all DAG automation workflows in the current workspace. "
            "Supports optional search query and limit."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Optional keyword to filter workflows by name or description.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max number of workflows to return (default: 50).",
                },
            },
            "additionalProperties": False,
        },
        risk_tier=RiskTier.safe,
        run=_workflow_list,
    )
)


# ---------------------------------------------------------------------------
# 2. workflow_get: Retrieve full details and DAG graph of a workflow
# ---------------------------------------------------------------------------
async def _workflow_get(args: dict[str, Any], ctx: ToolContext) -> str:
    """Get complete configuration, nodes, and edges of a workflow by ID or Name."""
    workflow_id = (args.get("workflow_id") or "").strip()
    name = (args.get("name") or "").strip()

    if not workflow_id and not name:
        return "error: please provide either 'workflow_id' or 'name'"

    stmt = select(Workflow).where(Workflow.org_id == ctx.org_id)
    if workflow_id:
        stmt = stmt.where(Workflow.id == workflow_id)
    else:
        stmt = stmt.where(Workflow.name == name)

    if ctx.user_id:
        stmt = scope_to_owner(stmt, ctx.db, Workflow.created_by_user_id)

    res = await ctx.db.execute(stmt)
    wf = res.scalar_one_or_none()

    if wf is None:
        return (
            f"error: workflow not found with id='{workflow_id}' or name='{name}'"
        )

    graph = wf.graph or {}
    return json.dumps(
        {
            "id": wf.id,
            "name": wf.name,
            "description": wf.description or "",
            "graph": {
                "nodes": graph.get("nodes") or [],
                "edges": graph.get("edges") or [],
            },
            "created_at": wf.created_at.isoformat() if wf.created_at else None,
            "updated_at": wf.updated_at.isoformat() if wf.updated_at else None,
        },
        ensure_ascii=False,
        indent=2,
    )


register(
    ToolSpec(
        name="workflow_get",
        description=(
            "Get detailed definition, nodes, edges, and configuration of a workflow "
            "by workflow ID or name."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "workflow_id": {
                    "type": "string",
                    "description": "The unique ID of the workflow to inspect.",
                },
                "name": {
                    "type": "string",
                    "description": "The name of the workflow (alternative to workflow_id).",
                },
            },
            "additionalProperties": False,
        },
        risk_tier=RiskTier.safe,
        run=_workflow_get,
    )
)


# ---------------------------------------------------------------------------
# 3. workflow_run: Execute a workflow on-demand
# ---------------------------------------------------------------------------
async def _workflow_run(args: dict[str, Any], ctx: ToolContext) -> str:
    """Execute a DAG workflow and return the output and execution summary."""
    workflow_id = (args.get("workflow_id") or "").strip()
    name = (args.get("name") or "").strip()
    input_text = str(args.get("input") or "")

    if not workflow_id and not name:
        return "error: please provide either 'workflow_id' or 'name'"

    stmt = select(Workflow).where(Workflow.org_id == ctx.org_id)
    if workflow_id:
        stmt = stmt.where(Workflow.id == workflow_id)
    else:
        stmt = stmt.where(Workflow.name == name)

    if ctx.user_id:
        stmt = scope_to_owner(stmt, ctx.db, Workflow.created_by_user_id)

    res = await ctx.db.execute(stmt)
    wf = res.scalar_one_or_none()

    if wf is None:
        return (
            f"error: workflow not found with id='{workflow_id}' or name='{name}'"
        )

    from app.core.workflow.engine import run_workflow

    try:
        final_output, log, run_id = await run_workflow(
            workflow=wf,
            input_text=input_text,
            db=ctx.db,
            stream=False,
            user_id=ctx.user_id,
            timezone_name=ctx.timezone_name,
        )
    except Exception as exc:
        return f"error executing workflow '{wf.name}': {exc}"

    node_summaries = []
    for ev in log:
        if ev.get("event") == "node_done":
            node_data = ev.get("data") or {}
            node_summaries.append(
                f"✓ Node '{node_data.get('node_id')}': {str(node_data.get('output'))[:200]}"
            )
        elif ev.get("event") == "node_error":
            node_data = ev.get("data") or {}
            node_summaries.append(
                f"✗ Node '{node_data.get('node_id')}' ERROR: {node_data.get('message')}"
            )

    return json.dumps(
        {
            "status": "success",
            "workflow_id": wf.id,
            "workflow_name": wf.name,
            "run_id": run_id,
            "output": final_output,
            "nodes_executed": len(node_summaries),
            "execution_log": node_summaries,
        },
        ensure_ascii=False,
        indent=2,
    )


register(
    ToolSpec(
        name="workflow_run",
        description=(
            "Execute an existing DAG workflow by ID or name with input text, "
            "returning the final execution output and node logs."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "workflow_id": {
                    "type": "string",
                    "description": "The unique ID of the workflow to run.",
                },
                "name": {
                    "type": "string",
                    "description": "The name of the workflow to run (alternative to workflow_id).",
                },
                "input": {
                    "type": "string",
                    "description": "Input text or JSON payload to feed into the workflow entry node.",
                },
            },
            "additionalProperties": False,
        },
        risk_tier=RiskTier.safe,
        run=_workflow_run,
    )
)


# ---------------------------------------------------------------------------
# 4. workflow_create: Create a new DAG workflow
# ---------------------------------------------------------------------------
async def _workflow_create(args: dict[str, Any], ctx: ToolContext) -> str:
    """Create a new DAG workflow in the user's workspace."""
    name = (args.get("name") or "").strip()
    description = str(args.get("description") or "").strip()
    graph = args.get("graph") or {}

    if not name:
        return "error: 'name' is required"
    if not isinstance(graph, dict) or "nodes" not in graph:
        return "error: 'graph' must be an object with a 'nodes' array and optional 'edges' array"

    service = WorkflowService(ctx.db)
    try:
        wf = await service.create(
            org_id=ctx.org_id,
            data={
                "name": name,
                "description": description,
                "graph": graph,
            },
            user_id=ctx.user_id,
        )
        return json.dumps(
            {
                "status": "created",
                "id": wf.id,
                "name": wf.name,
                "description": wf.description,
                "node_count": len(graph.get("nodes", [])),
                "edge_count": len(graph.get("edges", [])),
            },
            ensure_ascii=False,
            indent=2,
        )
    except WorkflowValidationError as e:
        return f"validation error: {e.errors}"
    except IntegrityError:
        await ctx.db.rollback()
        return f"error: a workflow named '{name}' already exists in your workspace"
    except Exception as e:
        return f"error creating workflow: {e}"


register(
    ToolSpec(
        name="workflow_create",
        description=(
            "Create a new DAG workflow with nodes and edges in the current workspace."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Unique name for the new workflow.",
                },
                "description": {
                    "type": "string",
                    "description": "Summary of what the workflow does.",
                },
                "graph": {
                    "type": "object",
                    "description": "DAG graph structure containing 'nodes' (array of GraphNode) and 'edges' (array of GraphEdge).",
                    "properties": {
                        "nodes": {"type": "array", "items": {"type": "object"}},
                        "edges": {"type": "array", "items": {"type": "object"}},
                    },
                    "required": ["nodes"],
                },
            },
            "required": ["name", "graph"],
            "additionalProperties": False,
        },
        risk_tier=RiskTier.safe,
        run=_workflow_create,
    )
)


# ---------------------------------------------------------------------------
# 5. workflow_update: Update an existing DAG workflow
# ---------------------------------------------------------------------------
async def _workflow_update(args: dict[str, Any], ctx: ToolContext) -> str:
    """Update name, description, or graph of an existing workflow."""
    workflow_id = (args.get("workflow_id") or "").strip()
    if not workflow_id:
        return "error: 'workflow_id' is required"

    data: dict[str, Any] = {}
    if "name" in args and args["name"]:
        data["name"] = str(args["name"]).strip()
    if "description" in args:
        data["description"] = str(args["description"]).strip()
    if "graph" in args and isinstance(args["graph"], dict):
        data["graph"] = args["graph"]

    if not data:
        return "error: no update fields provided (name, description, or graph)"

    service = WorkflowService(ctx.db)
    try:
        wf = await service.update(org_id=ctx.org_id, id=workflow_id, data=data)
        return json.dumps(
            {
                "status": "updated",
                "id": wf.id,
                "name": wf.name,
                "description": wf.description,
                "node_count": len((wf.graph or {}).get("nodes", [])),
                "edge_count": len((wf.graph or {}).get("edges", [])),
            },
            ensure_ascii=False,
            indent=2,
        )
    except WorkflowValidationError as e:
        return f"validation error: {e.errors}"
    except IntegrityError:
        await ctx.db.rollback()
        return f"error: workflow name '{data.get('name')}' already exists"
    except Exception as e:
        return f"error updating workflow: {e}"


register(
    ToolSpec(
        name="workflow_update",
        description=(
            "Update an existing workflow's name, description, or DAG graph structure."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "workflow_id": {
                    "type": "string",
                    "description": "ID of the workflow to update.",
                },
                "name": {
                    "type": "string",
                    "description": "New name for the workflow.",
                },
                "description": {
                    "type": "string",
                    "description": "New description for the workflow.",
                },
                "graph": {
                    "type": "object",
                    "description": "Updated DAG graph with nodes and edges.",
                },
            },
            "required": ["workflow_id"],
            "additionalProperties": False,
        },
        risk_tier=RiskTier.safe,
        run=_workflow_update,
    )
)


# ---------------------------------------------------------------------------
# 6. workflow_delete: Delete a workflow
# ---------------------------------------------------------------------------
async def _workflow_delete(args: dict[str, Any], ctx: ToolContext) -> str:
    """Delete a workflow and clean up its installations."""
    workflow_id = (args.get("workflow_id") or "").strip()
    name = (args.get("name") or "").strip()

    if not workflow_id and not name:
        return "error: please provide either 'workflow_id' or 'name'"

    stmt = select(Workflow).where(Workflow.org_id == ctx.org_id)
    if workflow_id:
        stmt = stmt.where(Workflow.id == workflow_id)
    else:
        stmt = stmt.where(Workflow.name == name)

    if ctx.user_id:
        stmt = scope_to_owner(stmt, ctx.db, Workflow.created_by_user_id)

    res = await ctx.db.execute(stmt)
    wf = res.scalar_one_or_none()

    if wf is None:
        return f"error: workflow not found with id='{workflow_id}' or name='{name}'"

    # Clean up associated marketplace installation if exists
    inst = await ctx.db.scalar(
        select(WorkflowInstallation).where(
            WorkflowInstallation.org_id == ctx.org_id,
            WorkflowInstallation.workflow_id == wf.id,
        )
    )
    if inst:
        await ctx.db.delete(inst)
        await ctx.db.flush()

    service = WorkflowService(ctx.db)
    success = await service.delete(org_id=ctx.org_id, id=wf.id)
    if success:
        return f"Successfully deleted workflow '{wf.name}' (ID: {wf.id})."
    return f"Failed to delete workflow '{wf.name}'."


register(
    ToolSpec(
        name="workflow_delete",
        description="Delete a DAG workflow from the workspace by ID or name.",
        input_schema={
            "type": "object",
            "properties": {
                "workflow_id": {
                    "type": "string",
                    "description": "The unique ID of the workflow to delete.",
                },
                "name": {
                    "type": "string",
                    "description": "The name of the workflow to delete (alternative to workflow_id).",
                },
            },
            "additionalProperties": False,
        },
        risk_tier=RiskTier.safe,
        requires_approval=True,
        run=_workflow_delete,
    )
)


# ---------------------------------------------------------------------------
# 7. workflow_generate: AI-generate a DAG graph from prompt
# ---------------------------------------------------------------------------
async def _workflow_generate(args: dict[str, Any], ctx: ToolContext) -> str:
    """Generate a DAG workflow design from a natural language prompt."""
    prompt = (args.get("prompt") or "").strip()
    model_id = args.get("model_id") or ctx.model_id

    if not prompt:
        return "error: 'prompt' is required"

    service = WorkflowService(ctx.db)
    try:
        result = await service.generate_graph(
            org_id=ctx.org_id,
            prompt=prompt,
            model_id=model_id,
        )
        return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as e:
        return f"error generating workflow graph: {e}"


register(
    ToolSpec(
        name="workflow_generate",
        description=(
            "Generate a complete DAG workflow (nodes, edges, node parameters) "
            "from a natural language prompt using AI."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Description of the workflow to design (e.g. 'Read email, summarize, and post to Slack').",
                },
                "model_id": {
                    "type": "string",
                    "description": "Optional model ID to use for generation.",
                },
            },
            "required": ["prompt"],
            "additionalProperties": False,
        },
        risk_tier=RiskTier.safe,
        run=_workflow_generate,
    )
)


# ---------------------------------------------------------------------------
# 8. workflow_catalog_list: Search Workflow Marketplace templates
# ---------------------------------------------------------------------------
async def _workflow_catalog_list(args: dict[str, Any], ctx: ToolContext) -> str:
    """List available templates in the Workflow Marketplace catalog."""
    query = (args.get("query") or "").strip()
    category = (args.get("category") or "").strip()

    latest_version = (
        select(
            WorkflowTemplateVersion.template_id,
            func.max(WorkflowTemplateVersion.version).label("version"),
        )
        .join(
            WorkflowTemplate,
            WorkflowTemplate.id == WorkflowTemplateVersion.template_id,
        )
        .where(
            WorkflowTemplate.status == "published",
            WorkflowTemplateVersion.published_at.is_not(None),
        )
        .group_by(WorkflowTemplateVersion.template_id)
        .subquery()
    )

    filters = [
        WorkflowTemplate.status == "published",
        WorkflowTemplateVersion.published_at.is_not(None),
        WorkflowTemplateVersion.template_id == latest_version.c.template_id,
        WorkflowTemplateVersion.version == latest_version.c.version,
    ]
    if category:
        filters.append(WorkflowTemplateVersion.category == category)
    if query:
        pattern = f"%{query}%"
        filters.append(
            WorkflowTemplateVersion.name.ilike(pattern)
            | WorkflowTemplateVersion.description.ilike(pattern)
            | WorkflowTemplateVersion.outcome.ilike(pattern)
        )

    result = await ctx.db.execute(
        select(WorkflowTemplate, WorkflowTemplateVersion)
        .join(
            WorkflowTemplateVersion,
            WorkflowTemplateVersion.template_id == WorkflowTemplate.id,
        )
        .where(and_(*filters))
        .order_by(
            WorkflowTemplateVersion.category, WorkflowTemplateVersion.name
        )
    )
    rows = result.all()

    installed_result = await ctx.db.execute(
        select(WorkflowInstallation.template_key).where(
            WorkflowInstallation.org_id == ctx.org_id,
            WorkflowInstallation.owner_user_id == ctx.user_id,
            WorkflowInstallation.status != "archived",
        )
    )
    installed_keys = set(installed_result.scalars().all())

    items = []
    for template, version in rows:
        items.append(
            {
                "key": template.key,
                "name": version.name,
                "category": version.category,
                "description": version.description,
                "outcome": version.outcome,
                "installed": template.key in installed_keys,
            }
        )

    return json.dumps(
        {"templates": items, "count": len(items)}, ensure_ascii=False, indent=2
    )


register(
    ToolSpec(
        name="workflow_catalog_list",
        description="Search and list published templates from the Workflow Marketplace.",
        input_schema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search keyword for template name or outcome.",
                },
                "category": {
                    "type": "string",
                    "description": "Optional category filter.",
                },
            },
            "additionalProperties": False,
        },
        risk_tier=RiskTier.safe,
        run=_workflow_catalog_list,
    )
)


# ---------------------------------------------------------------------------
# 9. workflow_catalog_install: Install template from Marketplace
# ---------------------------------------------------------------------------
async def _workflow_catalog_install(
    args: dict[str, Any], ctx: ToolContext
) -> str:
    """Install a template from Marketplace into the user's personal workflows."""
    template_key = (args.get("template_key") or "").strip()
    name = (args.get("name") or "").strip()

    if not template_key:
        return "error: 'template_key' is required"

    # Find template and latest published version
    template = await ctx.db.scalar(
        select(WorkflowTemplate).where(
            WorkflowTemplate.key == template_key,
            WorkflowTemplate.status == "published",
        )
    )
    if template is None:
        return f"error: template '{template_key}' not found or not published"

    version = await ctx.db.scalar(
        select(WorkflowTemplateVersion)
        .where(
            WorkflowTemplateVersion.template_id == template.id,
            WorkflowTemplateVersion.published_at.is_not(None),
        )
        .order_by(WorkflowTemplateVersion.version.desc())
        .limit(1)
    )
    if version is None:
        return f"error: no published version found for template '{template_key}'"

    # Check for existing installation
    existing = await ctx.db.scalar(
        select(WorkflowInstallation).where(
            WorkflowInstallation.org_id == ctx.org_id,
            WorkflowInstallation.owner_user_id == ctx.user_id,
            WorkflowInstallation.template_key == template_key,
            WorkflowInstallation.status != "archived",
        )
    )
    if existing:
        return f"error: template '{template_key}' is already installed (Workflow ID: {existing.workflow_id})"

    target_name = name or version.name
    # Fallback to copy from DAG template or existing workflow
    from app.core.workflow.template_dags import TEMPLATE_DAGS

    template_dag = TEMPLATE_DAGS.get(template_key)
    if template_dag and template_dag.get("nodes"):
        import copy

        template_graph = {
            "nodes": copy.deepcopy(template_dag.get("nodes", [])),
            "edges": copy.deepcopy(template_dag.get("edges", [])),
        }
    else:
        # Fallback by matching source workflow name
        source_wf = await ctx.db.scalar(
            select(Workflow)
            .where(
                Workflow.org_id == ctx.org_id, Workflow.name == version.name
            )
            .order_by(Workflow.created_at.desc())
            .limit(1)
        )
        if source_wf and source_wf.graph:
            import copy

            template_graph = copy.deepcopy(source_wf.graph)
        else:
            template_graph = {"nodes": [], "edges": []}

    workflow = Workflow(
        id=gen_id(),
        org_id=ctx.org_id,
        created_by_user_id=ctx.user_id,
        name=target_name,
        description=f"Managed installation of {version.name}",
        graph=template_graph,
    )
    installation = WorkflowInstallation(
        id=gen_id(),
        org_id=ctx.org_id,
        owner_user_id=ctx.user_id,
        template_key=template_key,
        template_version=version.version,
        workflow_id=workflow.id,
        name=target_name,
        status="enabled",
        timezone=ctx.timezone_name or "Asia/Ho_Chi_Minh",
        schedule={},
        settings={},
    )
    ctx.db.add(workflow)
    ctx.db.add(installation)

    try:
        await ctx.db.commit()
        return json.dumps(
            {
                "status": "installed",
                "workflow_id": workflow.id,
                "workflow_name": workflow.name,
                "template_key": template_key,
                "message": f"Successfully installed '{target_name}' into your workflows.",
            },
            ensure_ascii=False,
            indent=2,
        )
    except IntegrityError:
        await ctx.db.rollback()
        return f"error: a workflow named '{target_name}' already exists in your workspace"
    except Exception as e:
        await ctx.db.rollback()
        return f"error installing template: {e}"


register(
    ToolSpec(
        name="workflow_catalog_install",
        description="Install a reusable template from the Workflow Marketplace into your personal workflows.",
        input_schema={
            "type": "object",
            "properties": {
                "template_key": {
                    "type": "string",
                    "description": "The unique key of the template to install.",
                },
                "name": {
                    "type": "string",
                    "description": "Optional custom name for your installed workflow copy.",
                },
            },
            "required": ["template_key"],
            "additionalProperties": False,
        },
        risk_tier=RiskTier.safe,
        run=_workflow_catalog_install,
    )
)
