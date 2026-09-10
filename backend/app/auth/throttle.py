"""Failed-login throttle for the shared-password gate.

Constant-time comparison protects against timing attacks; it does nothing about someone
simply trying passwords as fast as the network allows. A single shared secret with no
rate limit is brute-forceable, so failures are counted per client and the endpoint locks
out after a threshold.

Deliberately in-memory and therefore **per-process**: this app runs as a single Uvicorn
worker on a free-tier dyno, so a dict is the honest fit. Behind multiple replicas this
must move to Redis or the edge (Cloudflare / API-gateway rate limiting) — a per-instance
counter is not a rate limit when there are N instances. Noted in README §12.
"""
from __future__ import annotations

import time
from threading import Lock

# After this many failures inside the window, the client is locked out for the window.
MAX_FAILURES = 8
WINDOW_SECONDS = 300.0

_failures: dict[str, list[float]] = {}
_lock = Lock()


def _prune(timestamps: list[float], now: float) -> list[float]:
    return [t for t in timestamps if now - t < WINDOW_SECONDS]


def is_locked(client: str) -> bool:
    """True when this client has burned through its attempts inside the window."""
    now = time.time()
    with _lock:
        recent = _prune(_failures.get(client, []), now)
        if recent:
            _failures[client] = recent
        else:
            _failures.pop(client, None)
        return len(recent) >= MAX_FAILURES


def register_failure(client: str) -> int:
    """Record a failed attempt. Returns the number of failures inside the window."""
    now = time.time()
    with _lock:
        recent = _prune(_failures.get(client, []), now)
        recent.append(now)
        _failures[client] = recent
        return len(recent)


def reset(client: str) -> None:
    """Clear a client's failures after a successful login."""
    with _lock:
        _failures.pop(client, None)


def retry_after_seconds(client: str) -> int:
    """Seconds until this client's oldest counted failure ages out of the window."""
    now = time.time()
    with _lock:
        recent = _prune(_failures.get(client, []), now)
    if len(recent) < MAX_FAILURES:
        return 0
    return max(1, int(WINDOW_SECONDS - (now - min(recent))))
