# syntax=docker/dockerfile:1

# RAG microservice container.
# Boots with zero-dependency backends (in-memory vector store, local hashing
# embedder, in-memory BM25) so it serves real traffic with NO external services.
# Override via env to use Qdrant / Redis / OpenAI.

FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Copy project (pyproject references README.md; package extras need the tree).
COPY pyproject.toml README.md ./
COPY rag_service ./rag_service
COPY scripts ./scripts
COPY alembic ./alembic
COPY alembic.ini ./alembic.ini

# Install runtime + lightweight optional backends (parsers, openai, redis, networkx).
# sentence-transformers (heavy / pulls torch) is intentionally omitted; add the
# `sentence-transformers` extra if you need local semantic embeddings.
RUN pip install --upgrade pip && \
    pip install ".[parsers,openai,bm25-redis,graph-networkx]"

# Container defaults: run fully offline out of the box.
ENV RAG_ENV=production \
    RAG_LOG_FORMAT=json \
    RAG_VECTOR_STORE=memory \
    RAG_BM25_BACKEND=memory \
    RAG_EMBEDDER=simple \
    RAG_MCP_TRANSPORT=both \
    RAG_REST_HOST=0.0.0.0 \
    RAG_REST_PORT=8100 \
    RAG_MCP_HOST=0.0.0.0 \
    RAG_MCP_PORT=8101

EXPOSE 8100 8101

CMD ["python", "-m", "rag_service.main"]
