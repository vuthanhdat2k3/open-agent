from fastapi import APIRouter

from app.api.v1.routes import (
    agents,
    chat,
    debug,
    files,
    mcp,
    models,
    providers,
    sessions,
    workflows,
)

api_router = APIRouter()
api_router.include_router(providers.router)
api_router.include_router(models.router)
api_router.include_router(agents.router)
api_router.include_router(mcp.router)
api_router.include_router(workflows.router)
api_router.include_router(chat.router)
api_router.include_router(debug.router)
api_router.include_router(files.router)
api_router.include_router(sessions.router)
