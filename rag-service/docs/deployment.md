# RAG Service — Deployment Guide

> Instructions for running `rag-service` in Docker, docker-compose, and production.

---

## 1. Prerequisites

| Component | Version | Purpose |
|-----------|---------|---------|
| Python | ≥ 3.11 | Runtime |
| Qdrant | ≥ 1.7 | Vector store |
| Redis | ≥ 7.0 | Optional: BM25 backend, task queue |
| Neo4j | ≥ 5.0 | Optional: production graph store |
| Docker | ≥ 24 | Container runtime |

---

## 2. Directory Structure (deployed)

```
/opt/rag-service/
├── .env                    # production config
├── rag_service/            # application code
├── data/
│   ├── rag.db              # SQLite metadata
│   ├── bm25/               # BM25 pickle files
│   └── graphs/             # Graph JSON files (if enabled)
└── logs/
    └── rag-service.log
```

---

## 3. Docker

### 3.1 Dockerfile

```dockerfile
# Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system deps for PDF/DOCX parsing
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY pyproject.toml .
RUN pip install --no-cache-dir -e ".[all]"

# Copy application
COPY rag_service/ ./rag_service/
COPY alembic/ ./alembic/
COPY alembic.ini .

# Create data directories
RUN mkdir -p /app/data/bm25 /app/data/graphs /app/logs

# Non-root user
RUN useradd -m raguser && chown -R raguser:raguser /app
USER raguser

EXPOSE 8100 8101

CMD ["python", "-m", "rag_service.main"]
```

### 3.2 Build and Run

```bash
docker build -t rag-service:latest .

docker run -d \
  --name rag-service \
  -p 8100:8100 \
  -p 8101:8101 \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/.env:/app/.env:ro \
  rag-service:latest
```

---

## 4. Docker Compose (recommended)

### 4.1 Full Stack (with Qdrant + Redis)

```yaml
# docker-compose.yml
version: "3.9"

services:
  rag-service:
    build: .
    image: rag-service:latest
    container_name: rag-service
    restart: unless-stopped
    ports:
      - "8100:8100"   # REST admin API
      - "8101:8101"   # MCP SSE server
    volumes:
      - rag_data:/app/data
      - ./logs:/app/logs
      - ./.env:/app/.env:ro
    environment:
      - RAG_QDRANT_URL=http://qdrant:6333
      - RAG_REDIS_URL=redis://redis:6379
      - RAG_ARQ_REDIS_URL=redis://redis:6379
    depends_on:
      qdrant:
        condition: service_healthy
      redis:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8100/api/v1/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  qdrant:
    image: qdrant/qdrant:v1.7.4
    container_name: rag-qdrant
    restart: unless-stopped
    ports:
      - "6333:6333"
      - "6334:6334"   # gRPC
    volumes:
      - qdrant_data:/qdrant/storage
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:6333/health"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    container_name: rag-redis
    restart: unless-stopped
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

volumes:
  rag_data:
  qdrant_data:
  redis_data:
```

### 4.2 Minimal (SQLite + in-memory BM25)

```yaml
# docker-compose.minimal.yml
version: "3.9"

services:
  qdrant:
    image: qdrant/qdrant:v1.7.4
    ports:
      - "6333:6333"
    volumes:
      - qdrant_data:/qdrant/storage

  rag-service:
    build: .
    ports:
      - "8100:8100"
      - "8101:8101"
    volumes:
      - rag_data:/app/data
      - ./.env:/app/.env:ro
    environment:
      - RAG_QDRANT_URL=http://qdrant:6333
      - RAG_BM25_BACKEND=memory
      - RAG_INGEST_QUEUE=memory
    depends_on:
      - qdrant

volumes:
  qdrant_data:
  rag_data:
```

### 4.3 Run

```bash
# Start full stack
docker-compose up -d

# View logs
docker-compose logs -f rag-service

# Stop
docker-compose down

# Stop and remove volumes (data loss!)
docker-compose down -v
```

---

## 5. Startup Sequence

The service startup (`rag_service/main.py`) performs:

```
1. Load config from .env
2. Run Alembic migrations (alembic upgrade head)
3. Create default collection if not exists
4. Initialize embedder (test connection if OpenAI)
5. Initialize vector store (create collections in Qdrant if not exist)
6. Load BM25 indexes from disk for all existing collections
7. Initialize graph store (if enabled)
8. Start REST admin API (uvicorn on RAG_REST_PORT)
9. Start MCP SSE server (uvicorn on RAG_MCP_PORT)  [if transport=sse or both]
10. MCP stdio server is started on-demand by client [if transport=stdio or both]
```

---

## 6. Production Checklist

### Security
- [ ] Set `RAG_API_KEY` to a strong random string
- [ ] Put MCP SSE behind a reverse proxy (nginx/Caddy) with TLS
- [ ] Restrict Qdrant port (6333) to internal network only
- [ ] Restrict Redis port to internal network only
- [ ] Set `RAG_CORS_ORIGINS` to exact frontend origins

### Performance
- [ ] Use `text-embedding-3-large` for highest quality (costs more)
- [ ] Set `RAG_QDRANT_ON_DISK=true` (default) for large collections
- [ ] Use `RAG_BM25_BACKEND=redis` for multi-instance deployments
- [ ] Set `RAG_INGEST_QUEUE=arq` for heavy ingest workloads
- [ ] Set `RAG_WORKERS=4` (Uvicorn) for concurrent REST requests

### Reliability
- [ ] Mount `rag_data` volume to persistent storage
- [ ] Enable Qdrant snapshot schedule (Qdrant Cloud or manual)
- [ ] Set up log rotation for `/app/logs/`
- [ ] Configure health check alerts

---

## 7. Nginx Reverse Proxy Example

```nginx
# /etc/nginx/sites-available/rag-service
server {
    listen 443 ssl;
    server_name rag.yourhost.com;

    ssl_certificate /etc/letsencrypt/live/rag.yourhost.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/rag.yourhost.com/privkey.pem;

    # REST admin API
    location /api/ {
        proxy_pass http://localhost:8100;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # MCP SSE endpoint
    location /sse {
        proxy_pass http://localhost:8101/sse;
        proxy_http_version 1.1;
        proxy_set_header Connection "";           # keep-alive for SSE
        proxy_set_header Cache-Control no-cache;
        proxy_buffering off;                      # disable buffering for SSE
        proxy_read_timeout 300s;
    }

    location /messages/ {
        proxy_pass http://localhost:8101/messages/;
        proxy_http_version 1.1;
    }
}
```

---

## 8. Upgrading

```bash
# Pull new code
git pull origin main

# Rebuild image
docker-compose build rag-service

# Restart (migrations run automatically on startup)
docker-compose up -d rag-service

# Verify health
curl http://localhost:8100/api/v1/health
```

**Note on BM25 index compatibility**: If `rank_bm25` version changes, BM25 pickle
files may be incompatible. Delete and rebuild:
```bash
docker-compose exec rag-service rm -rf /app/data/bm25/*.pkl
docker-compose restart rag-service
# Indexes are rebuilt from SQLite chunk data on next search
```
