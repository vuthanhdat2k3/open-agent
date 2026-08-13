from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OPENAGENT_", env_file=".env", extra="ignore")

    host: str = "127.0.0.1"
    port: int = 8000
    cors_origins: str = "http://localhost:3000"
    runtime: str = "local"

    # Database (async). SQLite for dev; postgres+asyncpg later.
    db_url: str = "sqlite+aiosqlite:///./openagent.db"
    # Postgres connection pool (per process — api and worker each hold their
    # own engine). Managed poolers (e.g. Supabase's pgbouncer in session mode)
    # cap total client connections; pool_size + max_overflow across every
    # process must stay under that cap or new connections start failing with
    # "max clients reached" — which also blocks unrelated requests like login.
    # Defaults: 2 processes * (3 + 2) = 10, leaving headroom under a 15-slot
    # pooler for psql/migrations/one-off scripts.
    db_pool_size: int = 3
    db_max_overflow: int = 2
    # Recycle connections periodically so a pooler-side idle/max-lifetime
    # disconnect surfaces as a clean reconnect instead of a stale-connection
    # error under load.
    db_pool_recycle_seconds: int = 1800

    # API key; empty => localhost-only mode.
    api_key: str = ""

    # Auth / JWT / OAuth configuration
    jwt_secret_key: str = "dev-secret-key-change-in-production"
    jwt_private_key_path: str = ""
    jwt_public_key_path: str = ""
    jwt_algorithm: str = "HS256"
    jwt_access_ttl_minutes: int = 15
    jwt_refresh_ttl_days: int = 30

    oauth_google_client_id: str = ""
    oauth_google_client_secret: str = ""
    oauth_github_client_id: str = ""
    oauth_github_client_secret: str = ""
    cookie_secure: bool = False

    # Workflow / agent-loop tuning
    max_agent_depth: int = 5
    max_iterations: int = 12
    workflow_execution_mode: Literal["inline", "queued"] = "inline"
    redis_url: str = "redis://127.0.0.1:6379/0"
    quota_requests_per_minute: int = 600
    quota_agent_runs_per_minute: int = 60
    quota_max_concurrent_runs: int = 10
    quota_monthly_cost_usd: float = 100.0
    quota_run_lease_ttl_seconds: int = 600
    quota_usage_cache_seconds: int = 15
    otel_enabled: bool = False
    otel_exporter_endpoint: str = ""
    # Attaching prompt/completion bodies to spans is opt-in: message content
    # routinely carries user PII and provider secrets, and the GenAI semantic
    # conventions treat content capture as an explicit choice.
    otel_capture_message_content: bool = False
    # LLM observability is independently switchable from OTel. Content is
    # captured after redaction by default when the feature is enabled; org,
    # agent, and request policy may only narrow this permission.
    observability_enabled: bool = False
    observability_capture_content: bool = True
    observability_sampling_rate: float = 1.0
    observability_max_content_bytes: int = 2 * 1024 * 1024
    langfuse_enabled: bool = False
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_base_url: str = ""
    langfuse_flush_timeout_seconds: float = 5.0
    log_format: Literal["json", "console"] = "json"
    budget_max_tool_calls: int = 40
    budget_max_cost_usd: float = 2.0
    budget_max_wall_seconds: float = 300.0
    budget_max_repeated_call: int = 3

    # Local filesystem sandbox for read_attachment
    workspace_dir: str = "./workspace"

    # Docker-isolated code execution (run_code tool)
    sandbox_enabled: bool = True
    sandbox_docker_image_python: str = "python:3.11-slim"
    sandbox_docker_image_bash: str = "bash:5"
    sandbox_memory: str = "256m"
    sandbox_cpus: float = 1.0
    sandbox_default_timeout: float = 30.0
    sandbox_max_run_seconds: float = 600.0
    sandbox_allow_network: bool = False
    sandbox_max_retries: int = 3

    max_upload_size: int = 25 * 1024 * 1024
    s3_endpoint_url: str = "http://minio:9000"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_bucket: str = "openagent-uploads"
    s3_region: str = "us-east-1"
    rag_mcp_server_name: str = "rag"

    # --- Customer Intelligence (email-driven company research) ---
    # Master switch for the feature; when disabled the API returns 404 for the
    # customer-intelligence router. Defaults OFF so the surface stays inert
    # until explicitly enabled.
    customer_intelligence_enabled: bool = False
    # Customer Intelligence MCP connector. Credentials are never stored here;
    # they are passed to the stateless MCP service for one call only.
    ci_mcp_server_name: str = "customer-intelligence"
    ci_mcp_transport: Literal["stdio", "sse"] = "sse"
    ci_mcp_url: str = "http://customer-intelligence-mcp:8301/sse"
    ci_mcp_command: str = ""
    ci_mcp_args: list[str] = []
    # Public API origin used in OAuth redirect URIs. This must be browser-
    # reachable and must match the URI registered in Google Cloud Console.
    ci_backend_public_url: str = "http://localhost:8000"
    ci_frontend_redirect_url: str = "http://localhost:3000/integrations"
    # News lookback window for web research (7/30/90 days).
    ci_news_window_days: int = 30

    # Self-hosted SearXNG metasearch instance backing the web_search tool.
    # Empty string disables it and falls back to the DuckDuckGo HTML scrape.
    searxng_url: str = "http://searxng:8080"
    # Self-hosted crawl4ai instance (JS-rendering crawler) backing web_fetch.
    # Empty string disables it and falls back to the plain httpx GET.
    crawler_url: str = "http://crawler:11235"
    crawler_api_token: str = ""
    # YouTube Data API v3 key backing the youtube_search tool. Empty string
    # disables the tool (it returns a clear "not configured" error).
    youtube_api_key: str = ""
    # Hard per-branch timeout for a single research call.
    ci_research_timeout_s: float = 30.0
    # Upper bound on persisted research sources per case (rate-limit guard).
    ci_max_sources_per_case: int = 25
    # Attachment size limit accepted during ingestion (defense-in-depth).
    ci_max_attachment_bytes: int = 10 * 1024 * 1024
    # How long a pending approval stays valid before it expires.
    ci_approval_expiry_hours: int = 72
    # Credential encryption at rest. Empty => use the legacy CI key, then
    # derive a stable development key from jwt_secret_key.
    credential_encryption_key: str = ""
    # Deprecated compatibility setting; keep it so existing deployments do
    # not lose access to encrypted CI credentials during migration.
    ci_credential_encryption_key: str = ""
    # Default daily run time (HH:MM, user timezone) for new connections.
    ci_daily_schedule_default: str = "08:00"
    # Google OAuth client credentials used by the real Gmail/Calendar/Drive connectors.
    ci_google_oauth_client_id: str = ""
    ci_google_oauth_client_secret: str = ""
    # Optional keyed company-identity source for the real company provider.
    # Empty => provider degrades to research_unavailable (no fabricated data).
    ci_company_api_url: str = ""
    ci_company_api_key: str = ""
    # Google Pub/Sub push authentication. Production must configure the OIDC
    # audience and allowed service account; a shared token is only for local
    # emulators/tests and is never accepted when OIDC is configured.
    gmail_pubsub_audience: str = ""
    gmail_pubsub_service_account: str = ""
    gmail_pubsub_shared_token: str = ""

    allowed_extensions: list[str] = [
        ".pdf",
        ".txt",
        ".md",
        ".csv",
        ".json",
        ".docx",
        ".html",
        ".htm",
        ".py",
        ".yaml",
        ".yml",
    ]

    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
