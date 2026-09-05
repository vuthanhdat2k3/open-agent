"""Per-process WORKER_ID (Fix #3 + #4).

Two processes importing the same module used to share the same
``WORKER_ID`` (a single random UUID computed at import time). The fix
embeds ``hostname-pid-rand`` so each process gets a stable, unique
identity. This is what stops heartbeat races when the system runs more
than one ARQ worker.
"""
from __future__ import annotations

import os
import socket

from app.core.workflow import resume


def test_worker_id_format() -> None:
    parts = resume._split_worker_id(resume.WORKER_ID)
    hostname, pid, rand = parts
    assert hostname == socket.gethostname()
    assert pid == str(os.getpid())
    assert len(rand) == 6
    assert all(c in "0123456789abcdef" for c in rand)


def test_two_consecutive_ids_differ() -> None:
    """Within the same process, the random suffix is fresh on every call —
    a worker that creates extra workers / arq tasks still gets distinct
    ids. (Production code only calls this once per process, but the
    function is allowed to be re-invoked safely.)
    """
    a = resume._process_worker_id()
    b = resume._process_worker_id()
    assert a != b
    # hostname + pid are the same; only the suffix differs.
    assert a.rsplit("-", 2)[0] == b.rsplit("-", 2)[0]
    assert a.rsplit("-", 2)[1] == b.rsplit("-", 2)[1]
    assert a.rsplit("-", 2)[2] != b.rsplit("-", 2)[2]


def test_split_handles_hostname_with_dashes() -> None:
    """Some hostnames contain dashes (e.g. ``DESKTOP-E00V6D8``). The parser
    must split on the last two separators only, otherwise the
    ``hostname`` portion is wrong."""
    worker_id = "DESKTOP-E00V6D8-12345-abc123"
    hostname, pid, rand = resume._split_worker_id(worker_id)
    assert hostname == "DESKTOP-E00V6D8"
    assert pid == "12345"
    assert rand == "abc123"


def test_module_level_worker_id_is_stable() -> None:
    """The module-level ``WORKER_ID`` constant is computed once at import
    time. The fix does not change that, but it must now be a valid
    ``hostname-pid-rand`` triple, not a bare UUID."""
    parts = resume._split_worker_id(resume.WORKER_ID)
    assert len(parts) == 3
    assert all(parts)
