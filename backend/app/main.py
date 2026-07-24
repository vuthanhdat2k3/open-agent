from contextlib import asynccontextmanager

from dotenv import load_dotenv
from redis.asyncio import from_url as redis_from_url
from sqlalchemy import text

load_dotenv()  # populate os.environ from .env (used as fallback when a provider's stored api_key is empty)

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.config import get_settings
from app.core.observability.logging import configure_logging, request_context_middleware
from app.core.observability.metrics import mount_metrics
from app.core.observability.tracing import init_tracing
from app.core.security import allowed_origins
from app.db.session import engine, init_db
from app.schemas.common import HealthResponse


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


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
    return HealthResponse()


@app.get("/api/health", response_model=HealthResponse)
async def api_health():
    return HealthResponse()


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


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
