from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()  # populate os.environ from .env (used as fallback when a provider's stored api_key is empty)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.observability.logging import configure_logging, request_context_middleware
from app.core.observability.metrics import mount_metrics
from app.core.observability.tracing import init_tracing
from app.core.security import allowed_origins
from app.db.session import init_db
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
