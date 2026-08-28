from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.sse import format_sse
from app.config import get_settings
from app.core.authz.scope import scope_to_owner
from app.core.quota.dependencies import agent_run_admission, enforce_resource_quota
from app.core.tools.registry import BUILTIN_TOOLS
from app.core.workflow.engine import create_workflow_run, run_workflow
from app.core.workflow.node_definitions import NODE_DEFINITIONS
from app.core.workflow.queue import enqueue_workflow_run
from app.db.base import utc_now
from app.db.session import SessionLocal
from app.dependencies import get_current_org_id, get_current_user, get_db, require_permission
from app.models.model import Model
from app.models.user import User
from app.models.workflow import Workflow
from app.models.workflow_installation import WorkflowInstallation
from app.models.workflow_node_run import WorkflowNodeRun
from app.models.workflow_run import WorkflowRun
from app.repositories.customer_intelligence import (
    CalendarConnectionRepository,
    DriveConnectionRepository,
    EmailConnectionRepository,
)
from app.schemas.workflow import (
    RunWorkflowRequest,
    WorkflowCreate,
    WorkflowGenerateRequest,
    WorkflowGenerateResponse,
    WorkflowOut,
    WorkflowUpdate,
    WorkflowValidationError,
)
from app.services.workflow_service import WorkflowService

router = APIRouter(
    prefix="/api/workflows",
    tags=["workflows"],
)


@router.get("/node-definitions", dependencies=[Depends(require_permission("workflows:read"))])
async def list_node_definitions():
    """Declarative config schemas for every node kind (single source of truth)."""
    return NODE_DEFINITIONS


@router.get("/node-options", dependencies=[Depends(require_permission("workflows:read"))])
async def list_node_options(
    type: str = "models",
    org_id: str = Depends(get_current_org_id),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Dynamic dropdown sources for ``load_options_from`` fields."""
    from app.repositories.agent_repo import AgentRepository

    if type == "models":
        rows = await db.execute(select(Model).where(Model.org_id == org_id, Model.enabled.is_(True)))
        return [{"name": m.display_name or m.name, "value": m.id} for m in rows.scalars().all()]
    if type == "agents":
        agents = await AgentRepository(db).list(org_id)
        return [
            {
                "name": a.name,
                "value": a.id,
                "system_prompt": a.system_prompt,
                "model_id": a.model_id,
                "tools": a.tools,
            }
            for a in agents
        ]
    if type == "workflows":
        rows = await db.execute(select(Workflow).where(Workflow.org_id == org_id))
        return [{"name": w.name, "value": w.id} for w in rows.scalars().all()]
    if type == "connections":
        out = []
        for repo in (EmailConnectionRepository, CalendarConnectionRepository, DriveConnectionRepository):
            conns = await repo(db).list(org_id)
            for c in conns:
                label = getattr(c, "account_email", None) or getattr(c, "provider", "connection")
                out.append({"name": f"{label} ({getattr(c, 'status', '')})", "value": c.id})
        return out
    if type == "users":
        rows = await db.execute(
            select(User).join(User.memberships).where(User.memberships.any(org_id=org_id))
        )
        return [{"name": u.email, "value": u.id} for u in rows.scalars().all()]
    if type == "categories":
        return []
    return []


@router.get("/tool-options", dependencies=[Depends(require_permission("workflows:read"))])
async def list_tool_options():
    """Registered tools for the tool-node dropdown (builtin + MCP + CI)."""
    tools = []
    for name, spec in BUILTIN_TOOLS.items():
        tools.append(
            {
                "name": name,
                "value": name,
                "description": getattr(spec, "description", ""),
                "risk_tier": getattr(spec, "risk_tier", "safe"),
                "input_schema": getattr(spec, "input_schema", {}),
            }
        )
    return tools


async def _run_workflow_detached(workflow_id: str, org_id: str, workflow_run_id: str) -> None:
    async with SessionLocal() as db:
        wf = await WorkflowService(db).get(org_id, workflow_id)
        run = await db.get(WorkflowRun, workflow_run_id)
        if wf is None or run is None or run.org_id != org_id:
            return
        try:
            await run_workflow(
                wf,
                str((run.input or {}).get("text", "")),
                db,
                stream=False,
                workflow_run_id=workflow_run_id,
                force_inline=True,
                user_id=run.triggered_by_user_id,
                timezone_name=(run.input or {}).get("timezone"),
            )
        except Exception as exc:  # noqa: BLE001
            run.status = "failed"
            run.error = str(exc)
            run.finished_at = utc_now()
            await db.commit()


@router.get("", response_model=list[WorkflowOut], dependencies=[Depends(require_permission("workflows:read"))])
async def list_workflows(
    all: bool = False,
    org_id: str = Depends(get_current_org_id),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    owner_id = None if all else current_user.id
    return await WorkflowService(db).list(org_id, created_by_user_id=owner_id)


@router.post(
    "",
    response_model=WorkflowOut,
    status_code=201,
    dependencies=[
        Depends(require_permission("workflows:create")),
        Depends(enforce_resource_quota("workflows")),
    ],
)
async def create_workflow(
    body: WorkflowCreate,
    org_id: str = Depends(get_current_org_id),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await WorkflowService(db).create(org_id, body.model_dump(), user_id=current_user.id)
    except WorkflowValidationError as e:
        raise HTTPException(400, detail={"errors": e.errors}) from e
    except ValueError as e:
        raise HTTPException(400, str(e))
    except IntegrityError as e:
        await db.rollback()
        error_msg = str(e.orig) if hasattr(e, "orig") else str(e)
        if "uq_workflows_org_user_name" in error_msg or "uq_workflows_org_name" in error_msg:
            raise HTTPException(409, f'Tên workflow "{body.name}" đã tồn tại. Vui lòng chọn một tên khác.') from e
        raise HTTPException(409, "Không thể lưu workflow do xung đột dữ liệu.") from e


@router.post(
    "/generate",
    response_model=WorkflowGenerateResponse,
    dependencies=[Depends(require_permission("workflows:create"))],
)
async def generate_workflow(
    body: WorkflowGenerateRequest,
    org_id: str = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await WorkflowService(db).generate_graph(org_id, body.prompt, body.model_id)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/{id}", response_model=WorkflowOut, dependencies=[Depends(require_permission("workflows:read"))])
async def get_workflow(
    id: str,
    org_id: str = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
):
    wf = await WorkflowService(db).get(org_id, id)
    if wf is None:
        raise HTTPException(404, "workflow not found")
    return wf


@router.put("/{id}", response_model=WorkflowOut, dependencies=[Depends(require_permission("workflows:update"))])
async def update_workflow(
    id: str,
    body: WorkflowUpdate,
    org_id: str = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
):
    # Ownership-scoped: role `user` may only update their own workflows.
    res = await db.execute(
        scope_to_owner(select(Workflow).where(Workflow.id == id, Workflow.org_id == org_id), db, Workflow.created_by_user_id)
    )
    if res.scalar_one_or_none() is None:
        existing = await db.scalar(select(Workflow.id).where(Workflow.id == id, Workflow.org_id == org_id))
        if existing is None:
            raise HTTPException(404, "workflow not found")
        raise HTTPException(403, "you can only edit workflows you created")
    try:
        result = await WorkflowService(db).update(org_id, id, body.model_dump(exclude_unset=True))
    except WorkflowValidationError as e:
        raise HTTPException(400, detail={"errors": e.errors}) from e
    except ValueError as e:
        raise HTTPException(404, str(e))
    except IntegrityError as e:
        await db.rollback()
        error_msg = str(e.orig) if hasattr(e, "orig") else str(e)
        if "uq_workflows_org_user_name" in error_msg or "uq_workflows_org_name" in error_msg:
            raise HTTPException(409, f'Tên workflow "{body.name}" đã tồn tại. Vui lòng chọn một tên khác.') from e
        raise HTTPException(409, "Không thể cập nhật workflow do xung đột dữ liệu.") from e
    # If this workflow belongs to a template installation and the user edited
    # its DAG, mark the installation so the worker runs the generic engine
    # instead of the catalog executor (the user now owns the graph).
    if body.graph is not None:
        installation = await db.scalar(
            select(WorkflowInstallation).where(
                WorkflowInstallation.workflow_id == id, WorkflowInstallation.org_id == org_id
            )
        )
        if installation is not None:
            settings = dict(installation.settings or {})
            settings["editor_overridden"] = True
            installation.settings = settings
            await db.commit()
    return result


@router.delete("/{id}", dependencies=[Depends(require_permission("workflows:delete"))])
async def delete_workflow(
    id: str,
    org_id: str = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
):
    # Ownership-scoped: role `user` may only delete their own workflows.
    res = await db.execute(
        scope_to_owner(select(Workflow).where(Workflow.id == id, Workflow.org_id == org_id), db, Workflow.created_by_user_id)
    )
    if res.scalar_one_or_none() is None:
        existing = await db.scalar(select(Workflow.id).where(Workflow.id == id, Workflow.org_id == org_id))
        if existing is None:
            raise HTTPException(404, "workflow not found")
        raise HTTPException(403, "you can only delete workflows you created")

    # Clean up associated marketplace installation if one exists
    inst = await db.scalar(
        select(WorkflowInstallation).where(
            WorkflowInstallation.org_id == org_id,
            WorkflowInstallation.workflow_id == id,
        )
    )
    if inst:
        await db.delete(inst)
        await db.flush()

    if not await WorkflowService(db).delete(org_id, id):
        raise HTTPException(404, "workflow not found")
    return {"ok": True}


@router.post(
    "/{id}/run",
    dependencies=[
        Depends(require_permission("workflows:run")),
        Depends(agent_run_admission),
    ],
)
async def run_workflow_endpoint(
    id: str,
    body: RunWorkflowRequest,
    background_tasks: BackgroundTasks,
    org_id: str = Depends(get_current_org_id),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    wf = await WorkflowService(db).get(org_id, id)
    if wf is None:
        raise HTTPException(404, "workflow not found")
    if not body.stream:
        output, log, workflow_run_id = await run_workflow(
            wf,
            body.input,
            db,
            stream=False,
            workflow_run_id=body.workflow_run_id,
            user_id=current_user.id,
            timezone_name=body.timezone,
            trigger_node_id=body.trigger_node_id,
            trigger_type="manual" if body.trigger_node_id else None,
        )
        return {"workflow_run_id": workflow_run_id, "output": output, "events": log}

    try:
        run = await create_workflow_run(
            wf,
            body.input,
            db,
            body.workflow_run_id,
            current_user.id,
            body.timezone,
            body.trigger_node_id,
            "manual" if body.trigger_node_id else None,
        )
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    run_id = run.id
    if run.status in {"succeeded", "failed", "diverged", "cancelled"}:
        run_status = run.status
    elif get_settings().workflow_execution_mode == "queued":
        run.status = "queued"
        await db.commit()
        await enqueue_workflow_run(run.id)
        run_status = "queued"
    else:
        background_tasks.add_task(_run_workflow_detached, wf.id, org_id, run.id)
        run_status = "running"

    async def gen():
        yield format_sse(
            {
                "event": "workflow_start",
                "data": {"workflow_run_id": run.id, "workflow_id": wf.id, "status": run_status},
            }
        )
        if run_status == "queued":
            yield format_sse({"event": "workflow_queued", "data": {"workflow_run_id": run.id}})
        elif run_status == "running":
            yield format_sse({"event": "workflow_attached", "data": {"workflow_run_id": run.id}})

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.post(
    "/runs/{run_id}/replay",
    dependencies=[Depends(require_permission("workflows:run"))],
)
async def replay_workflow_run(
    run_id: str,
    org_id: str = Depends(get_current_org_id),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Re-run a finished run against its recorded tool results.

    Deliberately not behind agent_run_admission: a replay executes no tools
    and makes no provider calls, so charging it against the run quota would
    penalise debugging.
    """
    res = await db.execute(
        scope_to_owner(
            select(WorkflowRun).where(WorkflowRun.id == run_id, WorkflowRun.org_id == org_id),
            db,
            WorkflowRun.triggered_by_user_id,
        )
    )
    source = res.scalar_one_or_none()
    if source is None:
        raise HTTPException(404, "workflow run not found")

    wf = await WorkflowService(db).get(org_id, source.workflow_id)
    if wf is None:
        raise HTTPException(404, "workflow not found")

    output, log, replay_run_id = await run_workflow(
        wf,
        (source.input or {}).get("text", ""),
        db,
        stream=False,
        force_inline=True,
        replay_of_run_id=source.id,
        user_id=current_user.id,
    )
    # A replay that took a different path is a real finding, not an error:
    # report it with the divergence point so the caller can see where.
    diverged = next((e for e in log if e["event"] == "replay_diverged"), None)
    return {
        "workflow_run_id": replay_run_id,
        "source_run_id": source.id,
        "output": output,
        "diverged": diverged["data"] if diverged else None,
        "events": log,
    }


@router.get("/runs/{run_id}", dependencies=[Depends(require_permission("workflows:read"))])
async def get_workflow_run(
    run_id: str,
    org_id: str = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(
        scope_to_owner(
            select(WorkflowRun).where(WorkflowRun.id == run_id, WorkflowRun.org_id == org_id),
            db,
            WorkflowRun.triggered_by_user_id,
        )
    )
    run = res.scalar_one_or_none()
    if run is None:
        raise HTTPException(404, "workflow run not found")
    node_res = await db.execute(
        select(WorkflowNodeRun)
        .where(WorkflowNodeRun.workflow_run_id == run.id)
        .order_by(WorkflowNodeRun.started_at, WorkflowNodeRun.attempt)
    )
    nodes = list(node_res.scalars().all())
    return {
        "id": run.id,
        "org_id": run.org_id,
        "workflow_id": run.workflow_id,
        "status": run.status,
        "input": run.input,
        "output": run.output,
        "error": run.error,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "nodes": [
            {
                "id": node.id,
                "node_id": node.node_id,
                "status": node.status,
                "attempt": node.attempt,
                "input": node.input,
                "output": node.output,
                "error": node.error,
                "started_at": node.started_at,
                "finished_at": node.finished_at,
            }
            for node in nodes
        ],
    }
