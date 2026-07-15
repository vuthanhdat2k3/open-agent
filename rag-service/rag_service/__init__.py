"""RAG Service — standalone Retrieval-Augmented Generation microservice.

Hybrid BM25 + semantic search with Reciprocal Rank Fusion, exposed via a
standard MCP server (stdio / SSE) and a REST admin API. Independent of
``open-agent``; couples only at runtime through the MCP protocol.
"""

__version__ = "1.0.0"
