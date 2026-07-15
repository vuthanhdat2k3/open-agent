"""RAG Service exception hierarchy.

All errors raised by the service extend :class:`RAGError` so callers (API routes,
MCP tools) can map them to HTTP status codes / MCP error payloads uniformly.
"""

from __future__ import annotations


class RAGError(Exception):
    """Base class for all RAG service errors."""

    code: str = "INTERNAL_ERROR"
    http_status: int = 500

    def __init__(self, message: str, *, detail: object | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail

    def to_dict(self) -> dict:
        return {"code": self.code, "message": self.message, "detail": self.detail}


class UnsupportedFormatError(RAGError):
    code = "UNSUPPORTED_FORMAT"
    http_status = 400

    def __init__(self, source_type: str) -> None:
        super().__init__(f"File type {source_type!r} is not supported")


class ParseError(RAGError):
    code = "PARSE_ERROR"
    http_status = 422


class EmptyDocumentError(RAGError):
    code = "EMPTY_DOCUMENT"
    http_status = 422


class EmbeddingError(RAGError):
    code = "EMBEDDING_ERROR"
    http_status = 503


class VectorStoreUnavailableError(RAGError):
    code = "VECTOR_STORE_UNAVAILABLE"
    http_status = 503


class BM25UnavailableError(RAGError):
    code = "BM25_UNAVAILABLE"
    http_status = 503


class CollectionNotFoundError(RAGError):
    code = "NOT_FOUND"
    http_status = 404

    def __init__(self, collection_id: str) -> None:
        super().__init__(f"Collection {collection_id!r} not found")


class DocumentNotFoundError(RAGError):
    code = "NOT_FOUND"
    http_status = 404

    def __init__(self, document_id: str) -> None:
        super().__init__(f"Document {document_id!r} not found")


class JobNotFoundError(RAGError):
    code = "NOT_FOUND"
    http_status = 404


class AlreadyExistsError(RAGError):
    code = "ALREADY_EXISTS"
    http_status = 409


class BadRequestError(RAGError):
    code = "BAD_REQUEST"
    http_status = 400


class ConfigurationError(RAGError):
    code = "CONFIGURATION_ERROR"
    http_status = 500
