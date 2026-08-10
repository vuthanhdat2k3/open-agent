from __future__ import annotations

import base64
import hashlib
import secrets

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import get_settings


def _encryption_key() -> bytes:
    settings = get_settings()
    raw = getattr(settings, "credential_encryption_key", "") or ""
    if not raw:
        raw = getattr(settings, "ci_credential_encryption_key", "") or ""
    if not raw:
        raw = settings.jwt_secret_key
    return hashlib.sha256(raw.encode("utf-8")).digest()


def encrypt_bytes(data: bytes) -> str:
    nonce = secrets.token_bytes(12)
    ciphertext = AESGCM(_encryption_key()).encrypt(nonce, data, None)
    return base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii")


def decrypt_bytes(token: str) -> bytes:
    raw = base64.urlsafe_b64decode(token.encode("ascii"))
    nonce, ciphertext = raw[:12], raw[12:]
    return AESGCM(_encryption_key()).decrypt(nonce, ciphertext, None)


def encrypt_string(value: str) -> str:
    return encrypt_bytes(value.encode("utf-8"))


def decrypt_string(token: str) -> str:
    return decrypt_bytes(token).decode("utf-8")
