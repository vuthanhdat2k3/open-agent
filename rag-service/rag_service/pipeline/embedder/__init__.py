"""Embedder re-exports (the factory imports these lazily)."""

from __future__ import annotations

from rag_service.pipeline.embedder.base import BaseEmbedder
from rag_service.pipeline.embedder.ollama import OllamaEmbedder
from rag_service.pipeline.embedder.openai import OpenAIEmbedder
from rag_service.pipeline.embedder.simple import SimpleEmbedder
from rag_service.pipeline.embedder.sentence_transformers import SentenceTransformerEmbedder

__all__ = [
    "BaseEmbedder",
    "OpenAIEmbedder",
    "OllamaEmbedder",
    "SentenceTransformerEmbedder",
    "SimpleEmbedder",
]
