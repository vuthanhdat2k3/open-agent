# syntax=docker/dockerfile:1

# RAG microservice container.
# Boots with zero-dependency backends (in-memory vector store, local hashing
# embedder, in-memory BM25) so it serves real traffic with NO external services.
# Override via env to use Qdrant / Redis / OpenAI.

FROM python:3.11-slim AS pdf-inspector-builder

# PyPI publishes a compatible manylinux cp38-abi3 wheel, but the application
# must install the fork at a commit SHA. VCS installs build from source, so
# keep Rust only in this build stage and copy the resulting wheel below.
ARG PDF_INSPECTOR_COMMIT=2543abe3715848589903754f30b5dca54f6b33a6
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl git pkg-config libssl-dev && rm -rf /var/lib/apt/lists/*
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --profile minimal
ENV PATH=/root/.cargo/bin:$PATH
RUN pip wheel --no-cache-dir --no-deps \
    "pdf-inspector @ git+https://github.com/vuthanhdat2k3/pdf-inspector.git@${PDF_INSPECTOR_COMMIT}" \
    --wheel-dir /wheels

FROM python:3.11-slim

# The application metadata pins pdf-inspector to a Git commit. pip resolves
# that VCS requirement again while installing the project, so git is required
# in the runtime image as well as the Rust build stage.
RUN apt-get update && apt-get install -y --no-install-recommends \
    git && rm -rf /var/lib/apt/lists/*

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
COPY --from=pdf-inspector-builder /wheels/pdf_inspector*.whl /tmp/

# Install runtime + optional backends with CPU-only PyTorch (prevents 3.5GB CUDA layer bloat).
RUN pip install --upgrade pip && \
    pip install /tmp/pdf_inspector*.whl && \
    pip install torch --index-url https://download.pytorch.org/whl/cpu && \
    pip install ".[parsers,openai,bm25-redis,graph-networkx,sentence-transformers]"

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
