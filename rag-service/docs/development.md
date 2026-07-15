# RAG Service — Development Guide

> Local setup, testing, and contributing guidelines.

---

## 1. Prerequisites

- Python ≥ 3.11
- Docker (for Qdrant)
- Git

---

## 2. Local Setup

```bash
# Clone
git clone <repo> rag-service
cd rag-service

# Create virtual environment
python -m venv .venv
source .venv/bin/activate          # Linux/macOS
# .venv\Scripts\activate           # Windows

# Install with all optional dependencies
pip install -e ".[dev,all]"

# Configure
cp .env.example .env
# Edit .env: set OPENAI_API_KEY, RAG_QDRANT_URL, etc.

# Start Qdrant (required)
docker run -d --name rag-qdrant -p 6333:6333 qdrant/qdrant:v1.7.4

# Run migrations and start
python scripts/run.py
# -> REST admin API: http://localhost:8100
# -> MCP SSE server: http://localhost:8101
# -> API docs:       http://localhost:8100/docs
```

---

## 3. pyproject.toml — Dependency Groups

```toml
[project]
name = "rag-service"
version = "1.0.0"
requires-python = ">=3.11"

dependencies = [
    # Core
    "fastapi>=0.110",
    "uvicorn[standard]>=0.27",
    "pydantic>=2.6",
    "pydantic-settings>=2.2",
    "sqlalchemy[asyncio]>=2.0",
    "aiosqlite>=0.19",
    "alembic>=1.13",
    "structlog>=24.0",

    # MCP
    "mcp>=1.0",

    # Retrieval
    "rank-bm25>=0.2.2",
    "qdrant-client>=1.7",

    # HTTP client (for URL ingest)
    "httpx>=0.26",
]

[project.optional-dependencies]
openai = ["openai>=1.14"]
ollama = ["httpx>=0.26"]           # uses httpx (already in core)
sentence-transformers = ["sentence-transformers>=2.6"]

parsers = [
    "pypdf2>=3.0",
    "pdfminer.six>=20221105",
    "python-docx>=1.1",
    "markdownify>=0.11",
    "chardet>=5.0",
    "python-frontmatter>=1.1",
]

bm25-redis = ["redis[asyncio]>=5.0"]
graph-networkx = ["networkx>=3.2"]
graph-neo4j = ["neo4j>=5.17"]
task-queue = ["arq>=0.25"]
metrics = ["prometheus-fastapi-instrumentator>=6.0"]

# Vietnamese BM25
pyvi = ["pyvi>=0.1.1"]

# "all" installs everything
all = [
    "rag-service[openai,parsers,bm25-redis,graph-networkx,task-queue,metrics]"
]

dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "pytest-cov>=4.1",
    "httpx>=0.26",        # TestClient
    "respx>=0.20",        # mock httpx
    "ruff>=0.3",
    "mypy>=1.9",
    "rich>=13.0",
]

[project.scripts]
rag-service = "rag_service.main:main"
rag-service-mcp = "rag_service.mcp_server.transport.stdio:main"

[tool.ruff]
line-length = 88
target-version = "py311"

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

---

## 4. scripts/run.py

```python
#!/usr/bin/env python
"""Development runner: migrate + start both servers."""
import asyncio, subprocess, sys, os

def run():
    # 1. Run Alembic migrations
    print("Running migrations...")
    result = subprocess.run(
        ["alembic", "upgrade", "head"],
        capture_output=False,
    )
    if result.returncode != 0:
        sys.exit(1)

    # 2. Seed default collection
    from rag_service.scripts.seed import seed_default_collection
    asyncio.run(seed_default_collection())

    # 3. Start both servers
    import uvicorn
    from rag_service.main import create_rest_app, create_mcp_sse_app

    # In dev: run sequentially using uvicorn programmatic API
    # In prod: use separate processes or Docker
    print("Starting RAG Service...")
    print("  REST admin API -> http://localhost:8100")
    print("  API docs       -> http://localhost:8100/docs")
    print("  MCP SSE        -> http://localhost:8101/sse")

    # Start REST (blocking in dev)
    uvicorn.run(
        "rag_service.main:rest_app",
        host="0.0.0.0", port=8100,
        reload=True, log_level="info",
    )

if __name__ == "__main__":
    run()
```

---

## 5. Project Structure Conventions

### Naming
- Files: `snake_case.py`
- Classes: `PascalCase`
- Functions/methods: `snake_case`
- Constants: `UPPER_SNAKE_CASE`
- IDs in DB: `"{prefix}_{hex8}"` — e.g., `"col_abc123"`, `"doc_xyz789"`

### Layer Rules
1. **Routes** (`api/v1/routes/`) — only call `services/`. No repo or core access.
2. **Services** (`services/`) — call repositories and pipeline/retrieval classes.
   No HTTP imports. No direct SQL.
3. **Repositories** (`repositories/`) — only SQLAlchemy. No business logic.
4. **Pipeline** (`pipeline/`) — pure data transformation. No DB access.
5. **Retrieval** (`retrieval/`) — search logic only. No HTTP routes.
6. **MCP tools** (`mcp_server/tools/`) — only call services. Handle all exceptions.

### Type Annotations
All functions must have full type annotations. Run `mypy` before committing.

---

## 6. Testing

### Test Layout

```
tests/
├── conftest.py           # shared fixtures
├── unit/
│   ├── pipeline/
│   │   ├── test_parser.py
│   │   ├── test_chunker.py
│   │   └── test_embedder.py
│   ├── retrieval/
│   │   ├── test_bm25.py
│   │   ├── test_rrf.py
│   │   └── test_hybrid_retriever.py
│   └── mcp/
│       └── test_mcp_tools.py
└── integration/
    ├── test_ingest_file.py
    ├── test_ingest_url.py
    ├── test_retrieval.py
    └── test_mcp_server.py
```

### conftest.py (key fixtures)

```python
# tests/conftest.py
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

from rag_service.main import rest_app
from rag_service.db.base import Base

@pytest_asyncio.fixture
async def db_session():
    """In-memory SQLite for each test."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with AsyncSession(engine) as session:
        yield session
    await engine.dispose()

@pytest_asyncio.fixture
async def client(db_session):
    """FastAPI test client with in-memory DB."""
    async with AsyncClient(
        transport=ASGITransport(app=rest_app),
        base_url="http://test",
    ) as c:
        yield c

@pytest.fixture
def mock_embedder(mocker):
    """Returns fixed 1536-dim zero vectors."""
    async def embed(texts):
        return [[0.0] * 1536 for _ in texts]
    async def embed_query(text):
        return [0.0] * 1536
    m = mocker.MagicMock()
    m.embed = embed
    m.embed_query = embed_query
    m.dimensions = 1536
    return m

@pytest.fixture
def mock_vector_store(mocker):
    """In-memory dict-based vector store."""
    return InMemoryVectorStore()  # test double
```

### Running Tests

```bash
# All tests
pytest

# With coverage
pytest --cov=rag_service --cov-report=html

# Unit tests only
pytest tests/unit/

# Specific test file
pytest tests/unit/retrieval/test_rrf.py -v

# Integration tests (requires running Qdrant)
pytest tests/integration/ --qdrant-url=http://localhost:6333
```

### Key Unit Tests

```python
# tests/unit/retrieval/test_rrf.py
from rag_service.retrieval.rrf import reciprocal_rank_fusion

def test_rrf_basic():
    list1 = [("A", 0.9), ("B", 0.8), ("C", 0.7)]
    list2 = [("B", 0.95), ("A", 0.85), ("D", 0.75)]
    result = reciprocal_rank_fusion([list1, list2], k=60)
    ids = [r[0] for r in result]
    # B appears at rank 1 in list2 and rank 2 in list1 → highest RRF score
    assert ids[0] == "B"
    assert "A" in ids
    assert "D" in ids

def test_rrf_single_list():
    list1 = [("A", 0.9), ("B", 0.8)]
    result = reciprocal_rank_fusion([list1], k=60)
    assert result[0][0] == "A"

def test_rrf_weighted():
    list1 = [("A", 0.9), ("B", 0.8)]
    list2 = [("B", 0.9), ("A", 0.8)]
    # Give 2x weight to list1
    result = reciprocal_rank_fusion([list1, list2], k=60, weights=[2.0, 1.0])
    # A has better rank in weighted list1 → should win
    assert result[0][0] == "A"
```

```python
# tests/unit/pipeline/test_chunker.py
from rag_service.pipeline.chunker.recursive import RecursiveCharacterChunker

def test_chunk_basic():
    text = "Hello world. " * 100  # 1300 chars
    chunker = RecursiveCharacterChunker(chunk_size=200, chunk_overlap=50)
    chunks = chunker.chunk(text, {})
    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk.text) <= 250  # allow small overrun at separator

def test_chunk_overlap():
    text = "ABCDEFGHIJ" * 10  # 100 chars
    chunker = RecursiveCharacterChunker(chunk_size=30, chunk_overlap=10)
    chunks = chunker.chunk(text, {})
    # Check overlap: end of chunk N overlaps with start of chunk N+1
    for i in range(len(chunks) - 1):
        assert chunks[i].text[-5:] in chunks[i+1].text
```

---

## 7. Linting and Type Checking

```bash
# Lint + format
ruff check rag_service/ tests/
ruff format rag_service/ tests/

# Type check
mypy rag_service/

# All checks (pre-commit)
ruff check . && ruff format --check . && mypy rag_service/
```

### pre-commit config (`.pre-commit-config.yaml`)

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.3.0
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format
```

---

## 8. Adding a New Parser

1. Create `rag_service/pipeline/parser/myformat.py`:
```python
from rag_service.pipeline.parser.base import Parser, ParseResult

class MyFormatParser(Parser):
    async def parse(self, source: bytes, **kwargs) -> ParseResult:
        text = ...  # your parsing logic
        metadata = {...}
        return ParseResult(text=text, metadata=metadata)
```

2. Register in `rag_service/pipeline/parser/__init__.py`:
```python
from .myformat import MyFormatParser
PARSER_REGISTRY["myext"] = MyFormatParser
```

3. Add tests in `tests/unit/pipeline/test_parser.py`.

---

## 9. Adding a New MCP Tool

1. Create handler in `rag_service/mcp_server/tools/`:
```python
def register_my_tools(server):
    @server.tool()
    async def rag_my_tool(param: str) -> str:
        try:
            # ... logic using services
            return "result"
        except Exception as e:
            return f"Error: {e}"
```

2. Register in `rag_service/mcp_server/server.py`:
```python
from rag_service.mcp_server.tools.my_tools import register_my_tools
register_my_tools(server)
```

3. Document the tool in `docs/rag-service/mcp-server.md`.

---

## 10. Useful Commands

```bash
# Check service health
curl http://localhost:8100/api/v1/health | python -m json.tool

# Ingest a test file
curl -X POST http://localhost:8100/api/v1/ingest/text \
  -H "Content-Type: application/json" \
  -d '{"text": "Test document content.", "title": "Test", "collection": "default"}'

# Test search
curl -X POST http://localhost:8100/api/v1/retrieve \
  -H "Content-Type: application/json" \
  -d '{"query": "test document", "collection": "default", "top_k": 3, "debug": true}'

# List collections
curl http://localhost:8100/api/v1/collections | python -m json.tool

# Run MCP stdio server manually (for testing)
python -m rag_service.mcp_server
# Then type MCP JSON-RPC messages to stdin
```
