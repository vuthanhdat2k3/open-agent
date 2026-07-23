from __future__ import annotations

import hashlib
import secrets


def generate_api_key() -> tuple[str, str, str]:
    """Generates an API key.

    Returns (full_key, key_prefix, key_hash)
    Example: full_key = "oa_live_a1b2c3d4..."
             key_prefix = "oa_live_a1b2"
             key_hash = sha256(full_key)
    """
    token = secrets.token_urlsafe(32)
    full_key = f"oa_live_{token}"
    prefix = full_key[:12]
    key_hash = hashlib.sha256(full_key.encode("utf-8")).hexdigest()
    return full_key, prefix, key_hash


def hash_api_key(full_key: str) -> str:
    return hashlib.sha256(full_key.encode("utf-8")).hexdigest()
