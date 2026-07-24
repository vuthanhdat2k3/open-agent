from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OPENAGENT_", env_file=".env", extra="ignore")

    host: str = "127.0.0.1"
    port: int = 8000
    cors_origins: str = "http://localhost:3000"

    # Database (async). SQLite for dev; postgres+asyncpg later.
    db_url: str = "sqlite+aiosqlite:///./openagent.db"

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
    sandbox_allow_network: bool = False
    sandbox_max_retries: int = 3

    upload_dir: str = "data/uploads"
    max_upload_size: int = 25 * 1024 * 1024
    rag_mcp_server_name: str = "rag"
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
