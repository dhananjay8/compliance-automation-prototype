"""Security hardening middleware: response headers and per-tenant rate limiting.

The rate limiter is an in-memory sliding-window counter keyed by
``(tenant-or-ip, minute-bucket)``. It is intentionally simple (no external
dependency) so it works in the single-process prototype deployment; for a
distributed production deployment this should be backed by Redis (the same
Redis instance already used by the job queue, see ``prototype/queue_backend.py``).
"""

from __future__ import annotations

import os
import time
from collections import defaultdict, deque

from fastapi import Request
from fastapi.responses import JSONResponse

RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "300"))
RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "1").lower() in ("1", "true", "yes")

_WINDOW_SECONDS = 60
_hits: dict[str, deque[float]] = defaultdict(deque)


def _client_key(request: Request) -> str:
    tenant_id = request.headers.get("x-tenant-id")
    if tenant_id:
        return f"tenant:{tenant_id}"
    client = request.client
    return f"ip:{client.host if client else 'unknown'}"


def _is_rate_limited(key: str) -> bool:
    now = time.monotonic()
    bucket = _hits[key]
    while bucket and now - bucket[0] > _WINDOW_SECONDS:
        bucket.popleft()
    if len(bucket) >= RATE_LIMIT_PER_MINUTE:
        return True
    bucket.append(now)
    return False


async def security_middleware(request: Request, call_next):
    """Combined rate-limit + security-header middleware."""
    if RATE_LIMIT_ENABLED and request.url.path.startswith("/api/"):
        key = _client_key(request)
        if _is_rate_limited(key):
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded, slow down."},
                headers={"Retry-After": "60"},
            )

    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-XSS-Protection"] = "0"
    response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    response.headers["Content-Security-Policy"] = "default-src 'self'"
    return response


def reset_rate_limit_state() -> None:
    """Test helper: clear in-memory rate limit buckets between test runs."""
    _hits.clear()
