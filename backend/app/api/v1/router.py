from fastapi import APIRouter, Depends

from app.api.v1.routes import (
    agents,
    approvals,
    auth,
    chat,
    debug,
    evaluations,
    files,
    mcp,
    models,
    orgs,
    providers,
    quotas,
    sessions,
    workflows,
)
from app.core.quota.dependencies import enforce_request_quota

api_router = APIRouter()
api_router.include_router(auth.router)
protected_router = APIRouter(dependencies=[Depends(enforce_request_quota)])
protected_router.include_router(orgs.router)
protected_router.include_router(quotas.router)
protected_router.include_router(providers.router)
protected_router.include_router(models.router)
protected_router.include_router(agents.router)
protected_router.include_router(approvals.router)
protected_router.include_router(mcp.router)
protected_router.include_router(workflows.router)
protected_router.include_router(chat.router)
protected_router.include_router(debug.router)
protected_router.include_router(evaluations.router)
protected_router.include_router(files.router)
protected_router.include_router(sessions.router)
api_router.include_router(protected_router)
