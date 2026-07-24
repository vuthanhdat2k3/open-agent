from fastapi import APIRouter

from app.api.v1.routes import (
    agents,
    approvals,
    auth,
    chat,
    debug,
    files,
    mcp,
    models,
    orgs,
    providers,
    sessions,
    workflows,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(orgs.router)
api_router.include_router(providers.router)
api_router.include_router(models.router)
api_router.include_router(agents.router)
api_router.include_router(approvals.router)
api_router.include_router(mcp.router)
api_router.include_router(workflows.router)
api_router.include_router(chat.router)
api_router.include_router(debug.router)
api_router.include_router(files.router)
api_router.include_router(sessions.router)
