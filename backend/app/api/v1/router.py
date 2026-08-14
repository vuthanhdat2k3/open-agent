from fastapi import APIRouter, Depends

from app.api.v1.routes import (
    a2a,
    agents,
    approvals,
    auth,
    chat,
    customer_intelligence,
    debug,
    email_intelligence_admin,
    evaluations,
    files,
    mcp,
    models,
    orgs,
    providers,
    quotas,
    sandbox,
    sessions,
    trusted_rules,
    workflows,
    workflow_catalog,
    workflow_installations,
    workspace,
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
protected_router.include_router(customer_intelligence.router)
protected_router.include_router(email_intelligence_admin.router)
protected_router.include_router(trusted_rules.router)
protected_router.include_router(mcp.router)
protected_router.include_router(workflows.router)
protected_router.include_router(workflow_catalog.router)
protected_router.include_router(workflow_installations.router)
protected_router.include_router(chat.router)
protected_router.include_router(debug.router)
protected_router.include_router(evaluations.router)
protected_router.include_router(files.router)
protected_router.include_router(sessions.router)
protected_router.include_router(sandbox.router)
protected_router.include_router(workspace.router)
protected_router.include_router(a2a.router)
api_router.include_router(customer_intelligence.oauth_router)
api_router.include_router(customer_intelligence.webhook_router)
api_router.include_router(protected_router)
