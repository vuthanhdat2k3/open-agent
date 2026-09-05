"""Tenant-scoped RAG collection naming.

The standalone rag-service has no tenant concept of its own — a
``Collection`` row is keyed only by its name, and Qdrant has no notion of
"org" or "user" in its filter schema. Every isolation boundary (org, and
within an org, personal-vs-shared) is therefore enforced purely by which
collection name a caller is allowed to read/write, decided here at the
trusted OpenAgent boundary — never from an LLM-supplied argument.

Two scopes exist per organization:
  - shared:   ``org-<org_id>-<collection>``                — operator/admin
              ingests and anything visible to the whole org.
  - personal: ``org-<org_id>-user-<user_id>-<collection>``  — a plain
              ``user``'s own ingests, readable only by that same user.

A ``user``'s effective search scope is therefore the union of both
collections; staff (operator/org_admin/platform_admin) only ever read/write
the shared one. Both entry points that talk to rag-service — chat/agent
tool calls (``backend/app/mcp/client.py``) and Files-UI ingest
(``backend/app/services/file_ingestion_service.py``) — call
``resolve_rag_collection`` so neither can bypass this.
"""

from __future__ import annotations

from typing import Any

ORG_COLLECTION_PREFIX = "org-"
CI_KNOWLEDGE_COLLECTION_PREFIX = "ci-knowledge-"


def resolve_rag_collection(
    collection: Any, org_id: str | None, *, personal_user_id: str | None = None
) -> Any:
    if not isinstance(collection, str) or not org_id:
        return collection
    if collection.startswith(CI_KNOWLEDGE_COLLECTION_PREFIX):
        return collection
    if personal_user_id:
        own_prefix = f"{ORG_COLLECTION_PREFIX}{org_id}-user-{personal_user_id}-"
    else:
        own_prefix = f"{ORG_COLLECTION_PREFIX}{org_id}-"
    if collection.startswith(own_prefix):
        # Already namespaced for this exact scope (e.g. the model echoed
        # back a collection name from a prior tool result) — don't double-prefix.
        return collection
    return f"{own_prefix}{collection}"
