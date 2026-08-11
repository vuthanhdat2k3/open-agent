from __future__ import annotations

import ipaddress
import re
import socket
import urllib.parse
from json import dumps as _json_dumps
from json import loads as _json_loads
from typing import Any

from app.core.credential_secrets import decrypt_bytes, encrypt_bytes

_PROMPT_INJECTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(
        r"ignore (all |any |the )?(previous|prior|above|earlier) (instructions|prompts|messages)",
        re.I,
    ),
    re.compile(r"\bsystem( prompt| instruction)s?\b[:\-]?", re.I),
    re.compile(r"you are now|act as a (human|developer|without restrictions|jailbroken)", re.I),
    re.compile(r"reveal (your|the) (system )?(prompt|instructions|secret|api ?key)", re.I),
    re.compile(r"exfiltrate|steal( the)? (api ?key|secret|credentials|token)", re.I),
    re.compile(r"send (this|the (email|data|report)) to", re.I),
]


def encrypt_credentials(payload: dict[str, Any]) -> str:
    return encrypt_bytes(_json_dumps(payload).encode("utf-8"))


def decrypt_credentials(token: str) -> dict[str, Any]:
    loaded = _json_loads(decrypt_bytes(token).decode("utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("decrypted credentials are not an object")
    return loaded


def redact_secret(value: str, secret: str | None) -> str:
    if not secret:
        return value
    return value.replace(secret, "[REDACTED]")


def redact_oauth_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        k: ("[REDACTED]" if k in {"access_token", "refresh_token", "client_secret"} else v)
        for k, v in payload.items()
    }


def scan_for_prompt_injection(text: str) -> list[str]:
    flags: list[str] = []
    for pattern in _PROMPT_INJECTION_PATTERNS:
        if pattern.search(text):
            flags.append(pattern.pattern)
    return flags


def _is_blocked_ip(ip: str) -> bool:
    addr = ipaddress.ip_address(ip)
    return (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
        or str(addr).startswith("169.254")
    )


def assert_safe_url(url: str) -> str | None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return "scheme must be http:// or https://"
    host = parsed.hostname
    if not host:
        return "missing host"
    if host in {"169.254.169.254", "metadata.google.internal", "metadata"}:
        return "metadata endpoint blocked"
    try:
        if _is_blocked_ip(host):
            return "private/loopback/link-local address blocked"
    except ValueError:
        pass
    try:
        addresses = socket.getaddrinfo(host, None)
    except OSError:
        return "host does not resolve to a public address"
    if not addresses:
        return "host does not resolve to a public address"
    for address in addresses:
        try:
            if _is_blocked_ip(address[4][0]):
                return "host resolves to a non-public address"
        except (IndexError, ValueError):
            return "host has an invalid address"

    return None