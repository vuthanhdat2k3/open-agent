from contextlib import asynccontextmanager

import structlog
from dotenv import load_dotenv
from redis.asyncio import from_url as redis_from_url
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

load_dotenv()  # populate os.environ from .env (used as fallback when a provider's stored api_key is empty)

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.config import get_settings
from app.core.agents.sync import sync_system_agents_all_orgs
from app.core.observability.llm_trace import NoopSink, set_default_sink
from app.core.observability.logging import configure_logging, request_context_middleware
from app.core.observability.metrics import mount_metrics
from app.core.observability.tracing import init_tracing
from app.core.providers.sync import sync_system_providers_all_orgs
from app.core.security import allowed_origins
from app.core.workflow.sync import sync_system_workflow_templates
from app.db.session import SessionLocal, engine, get_db, init_db
from app.schemas.common import HealthResponse

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    async with SessionLocal() as db:
        await sync_system_providers_all_orgs(db)
        await sync_system_agents_all_orgs(db)
        await sync_system_workflow_templates(db)
    sink = None
    settings = get_settings()
    if settings.observability_enabled and settings.langfuse_enabled:
        try:
            from app.core.observability.langfuse_sink import build_langfuse_sink

            sink = build_langfuse_sink(settings)
            if sink:
                set_default_sink(sink)
        except ModuleNotFoundError:
            # Observability must not take the API down when the optional SDK is
            # absent; production packaging can install it to enable the sink.
            await logger.awarning("langfuse_sdk_missing_observability_disabled")
    try:
        yield
    finally:
        if sink:
            sink.flush(settings.langfuse_flush_timeout_seconds)
        set_default_sink(NoopSink())


app = FastAPI(title="OpenAgent", version="0.1.0", lifespan=lifespan)
configure_logging()

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.middleware("http")(request_context_middleware)

app.include_router(api_router)
mount_metrics(app)
init_tracing(app)


@app.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(runtime=get_settings().runtime)


@app.get("/api/health", response_model=HealthResponse)
async def api_health():
    return HealthResponse(runtime=get_settings().runtime)


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


@app.get("/.well-known/agent-card.json")
async def well_known_agent_card(
    request: Request,
    org_id: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import select

    from app.a2a.card import generate_agent_card
    from app.models.agent import Agent

    header_org_id = request.headers.get("X-Org-Id") or org_id
    if not header_org_id:
        return generate_agent_card([], str(request.base_url))

    stmt = select(Agent).where(
        Agent.org_id == header_org_id,
        Agent.a2a_exposed.is_(True),
    )
    res = await db.execute(stmt)
    agents = list(res.scalars().all())
    return generate_agent_card(agents, str(request.base_url))



async def _check_db() -> None:
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))


async def _check_redis() -> None:
    client = redis_from_url(get_settings().redis_url)
    try:
        await client.ping()
    finally:
        await client.aclose()


@app.get("/readyz")
async def readyz():
    checks: dict[str, str] = {}
    try:
        await _check_db()
        checks["db"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["db"] = str(exc)
    try:
        await _check_redis()
        checks["redis"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["redis"] = str(exc)
    if any(value != "ok" for value in checks.values()):
        raise HTTPException(status_code=503, detail={"status": "unready", "checks": checks})
    return {"status": "ready", "checks": checks}
