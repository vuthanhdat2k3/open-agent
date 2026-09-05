from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.observability.audit import log_action
from app.core.quota.dependencies import agent_run_admission
from app.dependencies import get_current_org_id, get_db, require_permission
from app.evals.executor import LiveAgentExecutor, RecordedOutputExecutor
from app.schemas.evaluation import (
    EvaluationCaseApprove,
    EvaluationCaseCreate,
    EvaluationCaseOut,
    EvaluationComparisonOut,
    EvaluationResultOut,
    EvaluationRunCreate,
    EvaluationRunOut,
    EvaluationSuiteCreate,
    EvaluationSuiteOut,
    EvaluationSuiteUpdate,
)
from app.services.evaluation_service import (
    EvaluationService,
    recorded_outputs_from_payload,
)

router = APIRouter(prefix="/api/evaluations", tags=["evaluations"])


def _not_found_or_bad_request(exc: ValueError) -> HTTPException:
    detail = str(exc)
    return HTTPException(404 if "not found" in detail else 400, detail)


async def _suite_out(
    service: EvaluationService, org_id: str, suite, creator_email: str | None = None, creator_name: str | None = None,
) -> EvaluationSuiteOut:
    cases = await service.list_cases(org_id, suite.id, suite.dataset_version)
    return EvaluationSuiteOut(
        id=suite.id,
        name=suite.name,
        description=suite.description,
        agent_id=suite.agent_id,
        dataset_version=suite.dataset_version,
        created_by_user_id=suite.created_by_user_id,
        creator_email=creator_email,
        creator_name=creator_name,
        created_at=suite.created_at,
        updated_at=suite.updated_at,
        cases=[EvaluationCaseOut.from_orm_case(case) for case in cases],
    )


@router.get(
    "/suites",
    response_model=list[EvaluationSuiteOut],
    dependencies=[Depends(require_permission("evaluations:read"))],
)
async def list_suites(
    org_id: str = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
):
    from app.models.user import User

    service = EvaluationService(db)
    suites = await service.list_suites(org_id)

    # Join User to get creator email/name
    user_ids = [s.created_by_user_id for s in suites if s.created_by_user_id]
    user_map: dict[str, User] = {}
    if user_ids:
        res = await db.execute(select(User).where(User.id.in_(user_ids)))
        for u in res.scalars().all():
            user_map[u.id] = u

    return [
        await _suite_out(
            service,
            org_id,
            suite,
            creator_email=user_map[suite.created_by_user_id].email if suite.created_by_user_id and suite.created_by_user_id in user_map else None,
            creator_name=user_map[suite.created_by_user_id].display_name if suite.created_by_user_id and suite.created_by_user_id in user_map else None,
        )
        for suite in suites
    ]


@router.post(
    "/suites",
    response_model=EvaluationSuiteOut,
    status_code=201,
    dependencies=[Depends(require_permission("evaluations:manage"))],
)
async def create_suite(
    body: EvaluationSuiteCreate,
    request: Request,
    org_id: str = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
):
    service = EvaluationService(db)
    try:
        suite = await service.create_suite(
            org_id,
            body.model_dump(),
            getattr(request.state, "user_id", None),
        )
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(409, "evaluation suite name already exists") from exc
    except ValueError as exc:
        raise _not_found_or_bad_request(exc) from exc
    return await _suite_out(service, org_id, suite)


@router.get(
    "/suites/{suite_id}",
    response_model=EvaluationSuiteOut,
    dependencies=[Depends(require_permission("evaluations:read"))],
)
async def get_suite(
    suite_id: str,
    org_id: str = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
):
    service = EvaluationService(db)
    suite = await service.get_suite(org_id, suite_id)
    if suite is None:
        raise HTTPException(404, "evaluation suite not found")
    return await _suite_out(service, org_id, suite)


@router.put(
    "/suites/{suite_id}",
    response_model=EvaluationSuiteOut,
    dependencies=[Depends(require_permission("evaluations:manage"))],
)
async def update_suite(
    suite_id: str,
    body: EvaluationSuiteUpdate,
    org_id: str = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
):
    service = EvaluationService(db)
    try:
        suite = await service.update_suite(
            org_id, suite_id, body.model_dump(exclude_none=True)
        )
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(409, "evaluation suite name already exists") from exc
    except ValueError as exc:
        raise _not_found_or_bad_request(exc) from exc
    return await _suite_out(service, org_id, suite)


@router.delete(
    "/suites/{suite_id}",
    dependencies=[Depends(require_permission("evaluations:manage"))],
)
async def delete_suite(
    suite_id: str,
    org_id: str = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
):
    try:
        deleted = await EvaluationService(db).delete_suite(org_id, suite_id)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    if not deleted:
        raise HTTPException(404, "evaluation suite not found")
    return {"ok": True}


@router.post(
    "/suites/{suite_id}/cases",
    response_model=EvaluationCaseOut,
    status_code=201,
    dependencies=[Depends(require_permission("evaluations:manage"))],
)
async def add_case(
    suite_id: str,
    body: EvaluationCaseCreate,
    org_id: str = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
):
    try:
        case = await EvaluationService(db).add_case(
            org_id, suite_id, body.model_dump()
        )
    except ValueError as exc:
        raise _not_found_or_bad_request(exc) from exc
    return EvaluationCaseOut.from_orm_case(case)


@router.get(
    "/suites/{suite_id}/cases/proposed",
    response_model=list[EvaluationCaseOut],
    dependencies=[Depends(require_permission("evaluations:manage"))],
)
async def list_proposed_cases(
    suite_id: str,
    org_id: str = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
):
    try:
        cases = await EvaluationService(db).list_proposed_cases(org_id, suite_id)
    except ValueError as exc:
        raise _not_found_or_bad_request(exc) from exc
    return [EvaluationCaseOut.from_orm_case(c) for c in cases]


@router.post(
    "/cases/{case_id}/approve",
    response_model=EvaluationCaseOut,
    dependencies=[Depends(require_permission("evaluations:manage"))],
)
async def approve_case(
    case_id: str,
    body: EvaluationCaseApprove,
    request: Request,
    org_id: str = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
):
    try:
        case = await EvaluationService(db).approve_case(org_id, case_id, body.model_dump())
    except ValueError as exc:
        raise _not_found_or_bad_request(exc) from exc
    await log_action(
        db,
        org_id=org_id,
        actor_user_id=getattr(request.state, "user_id", None),
        action="evaluation.case.approved",
        resource_type="evaluation_case",
        resource_id=case.id,
        metadata={"suite_id": case.suite_id, "sampled_reason": case.sampled_reason},
    )
    return EvaluationCaseOut.from_orm_case(case)


@router.post(
    "/cases/{case_id}/reject",
    dependencies=[Depends(require_permission("evaluations:manage"))],
)
async def reject_case(
    case_id: str,
    org_id: str = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
):
    removed = await EvaluationService(db).reject_case(org_id, case_id)
    if not removed:
        raise HTTPException(404, "proposed evaluation case not found")
    return {"ok": True}


@router.get(
    "/suites/{suite_id}/runs",
    response_model=list[EvaluationRunOut],
    dependencies=[Depends(require_permission("evaluations:read"))],
)
async def list_runs(
    suite_id: str,
    org_id: str = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await EvaluationService(db).list_runs(org_id, suite_id)
    except ValueError as exc:
        raise _not_found_or_bad_request(exc) from exc


@router.post(
    "/suites/{suite_id}/runs",
    response_model=EvaluationRunOut,
    status_code=201,
    dependencies=[
        Depends(require_permission("evaluations:run")),
        Depends(agent_run_admission),
    ],
)
async def create_run(
    suite_id: str,
    body: EvaluationRunCreate,
    request: Request,
    org_id: str = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
):
    if body.execution_mode == "recorded":
        executor = RecordedOutputExecutor(
            recorded_outputs_from_payload(body.recorded_outputs)
        )
    else:
        if body.recorded_outputs:
            raise HTTPException(400, "live runs cannot include recorded outputs")
        executor = LiveAgentExecutor()
    service = EvaluationService(db)
    try:
        run = await service.create_run(
            org_id,
            suite_id,
            body.agent_release_id,
            executor,
            execution_mode=body.execution_mode,
            baseline_run_id=body.baseline_run_id,
            user_id=getattr(request.state, "user_id", None),
        )
    except ValueError as exc:
        raise _not_found_or_bad_request(exc) from exc
    await log_action(
        db,
        org_id=org_id,
        actor_user_id=getattr(request.state, "user_id", None),
        action="evaluation.run.complete",
        resource_type="evaluation_run",
        resource_id=run.id,
        metadata={
            "suite_id": suite_id,
            "release_id": run.agent_release_id,
            "pass_rate": run.pass_rate,
            "execution_mode": run.execution_mode,
        },
    )
    return run


@router.get(
    "/runs/{run_id}",
    response_model=EvaluationRunOut,
    dependencies=[Depends(require_permission("evaluations:read"))],
)
async def get_run(
    run_id: str,
    org_id: str = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
):
    run = await EvaluationService(db).get_run(org_id, run_id)
    if run is None:
        raise HTTPException(404, "evaluation run not found")
    return run


@router.get(
    "/runs/{run_id}/results",
    response_model=list[EvaluationResultOut],
    dependencies=[Depends(require_permission("evaluations:read"))],
)
async def list_results(
    run_id: str,
    org_id: str = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await EvaluationService(db).list_results(org_id, run_id)
    except ValueError as exc:
        raise _not_found_or_bad_request(exc) from exc


@router.get(
    "/runs/{candidate_id}/compare/{baseline_id}",
    response_model=EvaluationComparisonOut,
    dependencies=[Depends(require_permission("evaluations:read"))],
)
async def compare_runs(
    candidate_id: str,
    baseline_id: str,
    org_id: str = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await EvaluationService(db).compare_runs(
            org_id, candidate_id, baseline_id
        )
    except ValueError as exc:
        raise _not_found_or_bad_request(exc) from exc
