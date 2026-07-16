"""Structured memory schema contract.

This module is the single source of truth for how agent memory is normalized.
The model (LLM) MUST NOT invent its own keys — every `attribute` is validated
against a per-type whitelist and every alias is folded into a canonical
attribute. This is what prevents the duplicate-key root cause (name /
full_name / formal_name / display_name all collapsing to `profile.name`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


# Canonical memory types. Stored verbatim in `memory_type`.
MEMORY_TYPES: set[str] = {
    "profile",
    "preference",
    "project",
    "goal",
    "skill",
    "relationship",
    "history",
    "fact",
}

# Allowed `attribute` values per memory_type. Anything outside is rejected.
WHITELIST: dict[str, set[str]] = {
    "profile": {
        "name",
        "birthday",
        "email",
        "location",
        "occupation",
        "preferred_name",
    },
    "preference": {
        "language",
        "editor",
        "os",
        "timezone",
        "communication_style",
    },
    "project": {
        "current",
        "stack",
        "repo",
    },
    "goal": {
        "short_term",
        "long_term",
    },
    "skill": {
        "domain",
        "level",
    },
    "relationship": {
        "role",
        "notes",
    },
    "history": {
        "note",
    },
    "fact": {
        "statement",
    },
}

# Alias -> canonical (memory_type, attribute). Applied before whitelist check.
ALIASES: dict[str, tuple[str, str]] = {
    "full_name": ("profile", "name"),
    "formal_name": ("profile", "name"),
    "display_name": ("profile", "preferred_name"),
    "user_name": ("profile", "name"),
    "username": ("profile", "name"),
    "hoten": ("profile", "name"),
    "ten": ("profile", "name"),
    "ho_ten": ("profile", "name"),
    "preferred_language": ("preference", "language"),
    "favorite_language": ("preference", "language"),
    "favourite_language": ("preference", "language"),
    "favorite_editor": ("preference", "editor"),
    "current_project": ("project", "current"),
}

# Defaults used when the model omits optional fields.
DEFAULT_IMPORTANCE = 5
PROFILE_NAME_IMPORTANCE = 10
DEFAULT_CONFIDENCE = 1.0
DEFAULT_SOURCE = "agent"
DEFAULT_OWNER_TYPE = "agent"


@dataclass
class NormalizedMemory:
    memory_type: str
    attribute: str
    value: str
    importance: int
    confidence: float
    source: str


class MemorySchemaError(ValueError):
    """Raised when an attribute is not canonical and not whitelisted."""


def normalize(
    memory_type: str | None,
    attribute: str | None,
    value: str,
    importance: int | None = None,
    confidence: float | None = None,
    source: str | None = None,
) -> NormalizedMemory:
    """Validate and canonicalize a memory write request.

    Resolves aliases, enforces the whitelist, and fills defaults. Raises
    MemorySchemaError if the resulting (memory_type, attribute) is not allowed.
    """
    if not value or not str(value).strip():
        raise MemorySchemaError("value must not be empty")

    attr_raw = (attribute or "").strip().lower()
    mtype_raw = (memory_type or "").strip().lower()

    # Alias resolution takes precedence (it sets both type and attribute).
    if attr_raw in ALIASES:
        mtype_raw, attr_raw = ALIASES[attr_raw]

    if not mtype_raw:
        raise MemorySchemaError(
            "memory_type is required (e.g. 'profile', 'preference')"
        )
    if mtype_raw not in MEMORY_TYPES:
        raise MemorySchemaError(
            f"unknown memory_type '{mtype_raw}'. "
            f"allowed: {sorted(MEMORY_TYPES)}"
        )
    if not attr_raw:
        raise MemorySchemaError("attribute is required")

    allowed = WHITELIST.get(mtype_raw, set())
    if attr_raw not in allowed:
        raise MemorySchemaError(
            f"attribute '{attr_raw}' not allowed for memory_type '{mtype_raw}'. "
            f"allowed: {sorted(allowed)}"
        )

    if importance is None:
        importance = (
            PROFILE_NAME_IMPORTANCE
            if (mtype_raw == "profile" and attr_raw == "name")
            else DEFAULT_IMPORTANCE
        )
    if confidence is None:
        confidence = DEFAULT_CONFIDENCE
    if source is None or not source:
        source = DEFAULT_SOURCE

    return NormalizedMemory(
        memory_type=mtype_raw,
        attribute=attr_raw,
        value=str(value),
        importance=int(importance),
        confidence=float(confidence),
        source=source,
    )


def to_metadata_dict(conversation_id: str | None, message_id: str | None) -> dict[str, Any] | None:
    """Build the JSON metadata payload for traceability, or None if empty."""
    meta: dict[str, Any] = {}
    if conversation_id:
        meta["conversation_id"] = conversation_id
    if message_id:
        meta["message_id"] = message_id
    return meta or None
