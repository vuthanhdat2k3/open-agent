# RAG Service — MCP Server

> Design of the **Model Context Protocol (MCP) server** that exposes RAG capabilities
> to open-agent and any other MCP-compatible client.

---

## 1. Overview

The MCP server is the **primary public interface** of `rag-service`. It implements
the [MCP specification](https://spec.modelcontextprotocol.io/) using the official
`mcp` Python SDK in **server mode**.

```
MCP Client (open-agent)
        │
        │  MCP protocol (JSON-RPC 2.0)
        │
        ▼
  ┌─────────────────────────────────────────────┐
  │              MCP Server                      │
  │                                             │
  │  Tools:                                     │
  │   • rag_search          (retrieval)         │
  │   • rag_ingest_url      (ingest a URL)      │
  │   • rag_ingest_text     (ingest raw text)   │
  │   • rag_list_collections                    │
  │   • rag_delete_document                     │
  │                                             │
  │  Transports:                                │
  │   • stdio  (default, local)                 │
  │   • SSE    (HTTP, remote)                   │
  └─────────────────────────────────────────────┘
        │
        ▼
  RetrievalService / IngestService
```

---

## 2. Transport Options

### 2.1 stdio Transport (recommended for local use)

The MCP server reads from stdin and writes to stdout using JSON-RPC 2.0 framing.
This is the simplest, most secure option when client and server are on the same
machine.

**Entry point**:
```bash
python -m rag_service.mcp_server
# or via pyproject.toml script:
rag-service-mcp
```

**open-agent config**:
```json
{
  "name": "rag-service",
  "transport": "stdio",
  "command": "python",
  "args": ["-m", "rag_service.mcp_server"],
  "env": {
    "OPENAI_API_KEY": "sk-...",
    "QDRANT_URL": "http://localhost:6333"
  }
}
```

**Implementation**:
```python
# rag_service/mcp_server/transport/stdio.py
import asyncio
from mcp.server.stdio import stdio_server
from rag_service.mcp_server.server import create_mcp_server

async def main():
    server = create_mcp_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream,
                         server.create_initialization_options())

if __name__ == "__main__":
    asyncio.run(main())
```

### 2.2 SSE Transport (HTTP, for remote use)

The MCP server is mounted as a Starlette route on the REST admin API server.
SSE (Server-Sent Events) is used for the server→client stream; client→server uses
HTTP POST.

**Endpoint**: `GET /sse` — client connects here to start an MCP session.

**open-agent config**:
```json
{
  "name": "rag-service",
  "transport": "sse",
  "url": "http://localhost:8101/sse",
  "headers": {
    "X-API-Key": "your-optional-api-key"
  }
}
```

**Implementation**:
```python
# rag_service/mcp_server/transport/sse.py
from mcp.server.sse import SseServerTransport
from starlette.applications import Starlette
from starlette.routing import Route, Mount

def create_sse_app(mcp_server) -> Starlette:
    sse_transport = SseServerTransport("/messages")

    async def handle_sse(request):
        async with sse_transport.connect_sse(
            request.scope, request.receive, request._send
        ) as streams:
            await mcp_server.run(
                streams[0], streams[1],
                mcp_server.create_initialization_options()
            )

    return Starlette(routes=[
        Route("/sse", endpoint=handle_sse),
        Mount("/messages", app=sse_transport.handle_post_message),
    ])
```

### 2.3 Running Both Servers Together

```python
# rag_service/main.py
import uvicorn
from fastapi import FastAPI
from starlette.applications import Starlette
from starlette.routing import Mount

from rag_service.api.v1.router import api_router
from rag_service.mcp_server.transport.sse import create_sse_app
from rag_service.mcp_server.server import create_mcp_server

# REST admin API on port 8100
rest_app = FastAPI(title="RAG Service Admin API")
rest_app.include_router(api_router, prefix="/api/v1")

# MCP SSE server on port 8101
mcp_server = create_mcp_server()
mcp_app = create_sse_app(mcp_server)

if __name__ == "__main__":
    import threading
    # Start REST on 8100
    t1 = threading.Thread(target=uvicorn.run, kwargs={"app": rest_app, "port": 8100})
    # Start MCP SSE on 8101
    t2 = threading.Thread(target=uvicorn.run, kwargs={"app": mcp_app, "port": 8101})
    t1.start(); t2.start()
    t1.join(); t2.join()
```

---

## 3. Tool Definitions

### 3.1 `rag_search`

**Description**: Search the RAG knowledge base using hybrid BM25 + semantic search
with RRF fusion. Returns the most relevant text chunks.

**Input schema**:
```json
{
  "type": "object",
  "properties": {
    "query": {
      "type": "string",
      "description": "The search query in natural language"
    },
    "collection": {
      "type": "string",
      "description": "Collection name to search in. Default: 'default'",
      "default": "default"
    },
    "top_k": {
      "type": "integer",
      "description": "Number of results to return (1-20)",
      "default": 5,
      "minimum": 1,
      "maximum": 20
    },
    "filters": {
      "type": "object",
      "description": "Optional metadata filters",
      "properties": {
        "source_type": {
          "type": "string",
          "enum": ["pdf", "docx", "url", "text", "markdown", "html"]
        },
        "tags": {
          "type": "array",
          "items": {"type": "string"}
        },
        "document_id": {
          "type": "string"
        }
      }
    },
    "enable_graph": {
      "type": "boolean",
      "description": "Enable LightRAG graph retrieval (slower, more thorough)",
      "default": false
    }
  },
  "required": ["query"]
}
```

**Output** (text content):
```
Found 3 results for: "how does authentication work"

[1] Score: 0.0892 | Source: pdf | Document: auth-design.pdf
Authentication uses JWT tokens issued by the /api/auth/login endpoint...

[2] Score: 0.0841 | Source: url | Document: https://docs.example.com/auth
The authentication flow requires the client to exchange credentials...

[3] Score: 0.0756 | Source: text | Document: notes-2024-01.md
OAuth 2.0 is used for third-party authentication. The flow begins...

---
Metadata: collection=default, bm25_candidates=50, semantic_candidates=50
```

**Implementation**:
```python
# rag_service/mcp_server/tools/search.py

@mcp_server.tool()
async def rag_search(
    query: str,
    collection: str = "default",
    top_k: int = 5,
    filters: dict | None = None,
    enable_graph: bool = False,
) -> str:
    try:
        results = await retrieval_service.search(
            query=query,
            collection_id=collection,
            top_k=top_k,
            filters=filters,
            enable_graph=enable_graph,
        )
        if not results:
            return f"No results found for: {query!r}"

        lines = [f"Found {len(results)} results for: {query!r}\n"]
        for i, r in enumerate(results, 1):
            lines.append(
                f"[{i}] Score: {r.score:.4f} | "
                f"Source: {r.source_type} | "
                f"Document: {r.metadata.get('source_name', r.document_id)}\n"
                f"{r.text}\n"
            )
        return "\n".join(lines)
    except Exception as e:
        return f"Search error: {e}"
```

---

### 3.2 `rag_ingest_url`

**Description**: Download and ingest a web URL into the RAG knowledge base.

**Input schema**:
```json
{
  "type": "object",
  "properties": {
    "url": {
      "type": "string",
      "format": "uri",
      "description": "URL to fetch and ingest"
    },
    "collection": {
      "type": "string",
      "default": "default"
    },
    "tags": {
      "type": "array",
      "items": {"type": "string"},
      "description": "Tags to attach to all chunks from this document"
    },
    "chunk_size": {
      "type": "integer",
      "default": 800,
      "description": "Max characters per chunk"
    },
    "chunk_overlap": {
      "type": "integer",
      "default": 150
    }
  },
  "required": ["url"]
}
```

**Output**:
```
Ingested: https://example.com/docs/intro
  Document ID: doc_abc123
  Chunks created: 42
  Collection: default
  Status: success
```

---

### 3.3 `rag_ingest_text`

**Description**: Ingest raw text directly into the RAG knowledge base.

**Input schema**:
```json
{
  "type": "object",
  "properties": {
    "text": {
      "type": "string",
      "description": "The text content to ingest"
    },
    "title": {
      "type": "string",
      "description": "A name/title for this document"
    },
    "collection": {
      "type": "string",
      "default": "default"
    },
    "tags": {
      "type": "array",
      "items": {"type": "string"}
    },
    "chunk_size": {
      "type": "integer",
      "default": 800
    },
    "chunk_overlap": {
      "type": "integer",
      "default": 150
    }
  },
  "required": ["text"]
}
```

---

### 3.4 `rag_list_collections`

**Description**: List all available collections in the RAG knowledge base.

**Input schema**: `{}` (no parameters)

**Output**:
```
Collections (3):

  default
    Documents: 47  |  Chunks: 1,203  |  Created: 2024-01-15
    Last updated: 2024-03-10

  project-alpha
    Documents: 12  |  Chunks: 341  |  Created: 2024-02-01
    Last updated: 2024-03-08

  research-papers
    Documents: 5  |  Chunks: 892  |  Created: 2024-03-01
    Last updated: 2024-03-09
```

---

### 3.5 `rag_delete_document`

**Description**: Delete a document and all its chunks from the knowledge base.

**Input schema**:
```json
{
  "type": "object",
  "properties": {
    "document_id": {
      "type": "string",
      "description": "Document ID to delete"
    },
    "collection": {
      "type": "string",
      "default": "default"
    }
  },
  "required": ["document_id"]
}
```

**Output**:
```
Deleted document doc_abc123
  Chunks removed: 42
  Collection: default
```

---

## 4. Server Factory

```python
# rag_service/mcp_server/server.py
from mcp.server import Server
from mcp.server.models import InitializationOptions

def create_mcp_server() -> Server:
    server = Server("rag-service")

    # Register all tools
    from rag_service.mcp_server.tools.search import register_search_tools
    from rag_service.mcp_server.tools.ingest import register_ingest_tools
    from rag_service.mcp_server.tools.collections import register_collection_tools

    register_search_tools(server)
    register_ingest_tools(server)
    register_collection_tools(server)

    return server
```

---

## 5. Error Handling in Tools

All MCP tools follow this pattern:

```python
@mcp_server.tool()
async def rag_search(query: str, ...) -> str:
    try:
        # ... tool logic ...
    except ValidationError as e:
        # Return descriptive error — never raise
        return f"Invalid parameters: {e}"
    except VectorStoreUnavailableError:
        return "Error: Vector store is unavailable. Check Qdrant connection."
    except EmbeddingError as e:
        return f"Error: Could not embed query. {e}"
    except Exception as e:
        logger.exception("Unexpected error in rag_search")
        return f"Unexpected error: {type(e).__name__}: {e}"
```

MCP tools **never raise exceptions** — all errors are returned as text responses.
The caller (LLM) sees the error message and can decide how to handle it.

---

## 6. MCP Server Capabilities Declaration

```python
InitializationOptions(
    server_name="rag-service",
    server_version="1.0.0",
    capabilities=ServerCapabilities(
        tools=ToolsCapability(listChanged=False),
        # No resources or prompts in v1
    )
)
```

---

## 7. Connecting from open-agent (Step by Step)

1. In open-agent UI, navigate to **MCP Servers**.
2. Click **Add Server**.
3. Choose transport:

**stdio** (recommended):
```
Name:     rag-service
Transport: stdio
Command:   python
Args:      -m rag_service.mcp_server
Env:       OPENAI_API_KEY=sk-...
           QDRANT_URL=http://localhost:6333
```

**SSE**:
```
Name:     rag-service
Transport: sse
URL:      http://localhost:8101/sse
```

4. Click **Connect**. open-agent will call `tools/list` and discover all 5 tools.
5. Grant the tools to any agent via **Agent → Tools → MCP → rag-service**.
6. The agent can now call `rag_search`, `rag_ingest_url`, etc. in its tool loop.

---

## 8. Tool Usage Examples (Agent Perspective)

```
User: "What does our docs say about rate limiting?"

Agent tool call:
  rag_search(
    query="rate limiting API",
    collection="default",
    top_k=5
  )

Response:
  [1] Score: 0.0921 | Source: pdf | Document: api-guidelines.pdf
  Rate limiting is enforced at 100 requests/minute per API key...
  ...

Agent reply: "According to your API guidelines, rate limiting is enforced at..."
```

```
User: "Add this page to the knowledge base: https://docs.example.com/changelog"

Agent tool call:
  rag_ingest_url(
    url="https://docs.example.com/changelog",
    collection="default",
    tags=["changelog", "updates"]
  )

Response: Ingested: https://docs.example.com/changelog | Chunks: 28 | Status: success

Agent reply: "Done! I've added the changelog page to your knowledge base (28 chunks)."
```
