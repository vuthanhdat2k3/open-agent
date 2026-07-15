"""RAG Service configuration.

All settings are read from environment variables (prefixed ``RAG_`` by default)
and an optional ``.env`` file, using :mod:`pydantic_settings`.

The documented external backends (Qdrant, OpenAI, Chroma, Redis, Neo4j) are
*optional*.  When they are not reachable the service factory
(:mod:`rag_service.core.factory`) transparently falls back to zero-dependency
in-process implementations so the service always boots and serves real traffic.
"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #
# Resolve relative to the project root (two levels up from this file:
# rag_service/config.py -> rag_service -> project root).
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = PROJECT_ROOT / "data"


class Settings(BaseSettings):
    """Service-wide configuration."""

    model_config = SettingsConfigDict(
        env_prefix="RAG_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ------------------------------------------------------------------ #
    # Core
    # ------------------------------------------------------------------ #
    env: str = "development"
    log_level: str = "INFO"
    log_format: str = "json"  # "json" | "console"
    api_key: str = ""  # admin REST key; empty = no auth (local only)
    cors_origins: str = "http://localhost:3000"

    # ------------------------------------------------------------------ #
    # Server
    # ------------------------------------------------------------------ #
    rest_host: str = "0.0.0.0"
    rest_port: int = 8100
    mcp_host: str = "0.0.0.0"
    mcp_port: int = 8101
    mcp_transport: str = "both"  # "stdio" | "sse" | "both"
    workers: int = 1

    # ------------------------------------------------------------------ #
    # Database
    # ------------------------------------------------------------------ #
    db_url: str = "sqlite+aiosqlite:///./rag.db"
    db_echo: bool = False
    data_dir: Path = DEFAULT_DATA_DIR
    bm25_persist_dir: Path = DEFAULT_DATA_DIR / "bm25"
    graph_persist_dir: Path = DEFAULT_DATA_DIR / "graphs"

    # ------------------------------------------------------------------ #
    # Embedding
    # ------------------------------------------------------------------ #
    embedder: str = "openai"  # "openai" | "ollama" | "sentence_transformers" | "simple"
    openai_api_key: str = ""  # also accepts OPENAI_API_KEY (see below)
    openai_base_url: str = "https://api.openai.com/v1"
    openai_embed_model: str = "text-embedding-3-small"
    openai_embed_dimensions: int = 1536
    openai_embed_batch_size: int = 100
    ollama_base_url: str = "http://localhost:11434"
    ollama_embed_model: str = "nomic-embed-text"
    st_model: str = "all-MiniLM-L6-v2"
    embed_retry_attempts: int = 3
    embed_retry_delay: float = 1.0

    # ------------------------------------------------------------------ #
    # Vector store
    # ------------------------------------------------------------------ #
    vector_store: str = "qdrant"  # "qdrant" | "chroma" | "memory"
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str = ""
    qdrant_timeout: int = 30
    qdrant_on_disk: bool = True
    chroma_path: Path = DEFAULT_DATA_DIR / "chroma"
    chroma_host: str | None = None
    chroma_port: int = 8000

    # ------------------------------------------------------------------ #
    # BM25
    # ------------------------------------------------------------------ #
    bm25_backend: str = "memory"  # "memory" | "redis"
    bm25_k1: float = 1.5
    bm25_b: float = 0.75
    bm25_epsilon: float = 0.25
    bm25_tokenizer: str = "whitespace"  # "whitespace" | "pyvi" | "jieba"
    redis_url: str = "redis://localhost:6379"

    # ------------------------------------------------------------------ #
    # Retrieval
    # ------------------------------------------------------------------ #
    rrf_k: int = 60
    rrf_bm25_weight: float = 1.0
    rrf_semantic_weight: float = 1.0
    default_top_k: int = 5
    default_candidate_k: int = 50
    query_cache_size: int = 1000
    query_hyde: bool = False
    query_hyde_model: str = "gpt-4o-mini"

    # ------------------------------------------------------------------ #
    # Graph (optional)
    # ------------------------------------------------------------------ #
    enable_graph: bool = False
    graph_backend: str = "networkx"  # "networkx" | "neo4j"
    graph_llm_model: str = "gpt-4o-mini"
    graph_max_entities: int = 50
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = ""

    # ------------------------------------------------------------------ #
    # Chunking defaults
    # ------------------------------------------------------------------ #
    default_chunk_size: int = 800
    default_chunk_overlap: int = 150
    default_chunker: str = "recursive"

    # ------------------------------------------------------------------ #
    # Task queue
    # ------------------------------------------------------------------ #
    ingest_async: bool = True
    ingest_queue: str = "memory"  # "memory" | "arq"
    ingest_workers: int = 2
    arq_redis_url: str = "redis://localhost:6379"

    # ------------------------------------------------------------------ #
    # Validation / derived
    # ------------------------------------------------------------------ #
    @property
    def openai_key_effective(self) -> str:
        """OpenAI key — accepts both ``RAG_OPENAI_API_KEY`` and ``OPENAI_API_KEY``."""
        return self.openai_api_key or _env_openai_key()

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.bm25_persist_dir, self.graph_persist_dir, self.chroma_path):
            try:
                d.mkdir(parents=True, exist_ok=True)
            except Exception:  # pragma: no cover - best effort
                pass


def _env_openai_key() -> str:
    import os

    return os.environ.get("OPENAI_API_KEY", "")


# Single shared instance used across the service.
settings = Settings()
