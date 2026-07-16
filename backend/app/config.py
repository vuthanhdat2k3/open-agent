from datetime import datetime, timezone
import uuid

from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="OPENAGENT_", env_file=".env", extra="ignore"
    )

    host: str = "127.0.0.1"
    port: int = 8000
    cors_origins: str = "http://localhost:3000"

    # Database (async). SQLite for dev; postgres+asyncpg later.
    db_url: str = "sqlite+aiosqlite:///./openagent.db"

    # API key; empty => localhost-only mode.
    api_key: str = ""

    # Workflow / agent-loop tuning
    max_agent_depth: int = 5
    max_iterations: int = 12
    loop_warn: int = 3
    loop_block: int = 5
    loop_circuit: int = 30

    # Local filesystem sandbox for read_attachment
    workspace_dir: str = "./workspace"

    upload_dir: str = "data/uploads"
    max_upload_size: int = 25 * 1024 * 1024
    rag_mcp_server_name: str = "rag"
    allowed_extensions: list[str] = [
        ".pdf", ".txt", ".md", ".csv", ".json",
        ".docx", ".html", ".htm", ".py", ".yaml", ".yml",
    ]

    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
