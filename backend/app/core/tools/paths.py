from __future__ import annotations

import ipaddress
import os
import socket
from pathlib import Path
from urllib.parse import urlparse


def safe_resolve(workspace_dir: str, path: str) -> Path | None:
    """Resolve ``path`` against ``workspace_dir``, rejecting any escape.

    Returns the absolute ``Path`` if it stays inside the workspace, otherwise
    ``None``. Absolute ``path`` values are treated as relative to the workspace
    and still checked (so ``/etc/passwd`` is rejected), guarding against both
    ``..`` traversal and absolute-path injection.
    """
    base = os.path.abspath(workspace_dir)
    target = os.path.abspath(os.path.join(base, path))
    if target != base and not target.startswith(base + os.sep):
        return None
    return Path(target)


def safe_url(url: str) -> str | None:
    """Reject URLs whose host resolves to a non-public IP (SSRF guard).

    Returns ``url`` unchanged if every resolved address is a routable public
    IP over http(s); ``None`` if the scheme is wrong, the host doesn't
    resolve, or any resolved address is loopback/private/link-local (this
    also blocks cloud metadata endpoints like 169.254.169.254) /
    reserved/multicast/unspecified.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return None
    try:
        addrs = socket.getaddrinfo(parsed.hostname, None)
    except socket.gaierror:
        return None
    for _, _, _, _, sockaddr in addrs:
        ip = ipaddress.ip_address(sockaddr[0])
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            return None
    return url
