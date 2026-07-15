#!/usr/bin/env python
"""Run the RAG service.

Thin wrapper around :func:`rag_service.main.main` so the documented
``python scripts/run.py`` entry point works without a pip install. The
service is fully runnable with zero external services: it falls back to an
in-memory vector store, a local hashing embedder and an in-memory BM25 index
when Qdrant / OpenAI / Chroma are not configured.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make the project root importable when executed as a plain script.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rag_service.main import main  # noqa: E402


if __name__ == "__main__":
    main()
