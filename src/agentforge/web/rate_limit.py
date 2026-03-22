"""Simple in-process rate limiter for the AgentForge web API.

Uses a sliding-window counter per client IP. No external dependencies.

Configure via environment:
  - AGENTFORGE_RATE_LIMIT: requests per window (default: 20)
  - AGENTFORGE_RATE_WINDOW: window size in seconds (default: 60)
"""

from __future__ import annotations

import os
import time
import threading
from collections import defaultdict

from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

# Paths exempt from rate limiting
_EXEMPT_PREFIXES = ("/static/", "/api/docs", "/openapi.json")
_EXEMPT_PATHS = frozenset({"/", "/health"})

# Only rate-limit mutating/expensive endpoints
_RATE_LIMITED_PREFIXES = (
    "/api/extract",
    "/api/forge",
    "/api/batch",
    "/api/culture",
    "/api/settings/validate-key",
)


class _SlidingWindowCounter:
    """Thread-safe sliding window rate limiter."""

    def __init__(self, max_requests: int, window_seconds: int) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict[str, list[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def is_allowed(self, key: str) -> bool:
        now = time.monotonic()
        cutoff = now - self.window_seconds

        with self._lock:
            timestamps = self._requests[key]
            # Prune old entries
            self._requests[key] = [t for t in timestamps if t > cutoff]
            if len(self._requests[key]) >= self.max_requests:
                return False
            self._requests[key].append(now)
            return True

    def cleanup(self) -> None:
        """Remove stale entries to prevent memory growth."""
        now = time.monotonic()
        cutoff = now - self.window_seconds
        with self._lock:
            stale_keys = [
                k for k, v in self._requests.items()
                if not v or v[-1] < cutoff
            ]
            for k in stale_keys:
                del self._requests[k]


def _get_client_ip(request: Request) -> str:
    """Extract client IP, respecting X-Forwarded-For behind a reverse proxy."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# Module-level limiter (shared across requests in the same process)
_limiter = _SlidingWindowCounter(
    max_requests=int(os.environ.get("AGENTFORGE_RATE_LIMIT", "20")),
    window_seconds=int(os.environ.get("AGENTFORGE_RATE_WINDOW", "60")),
)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limits expensive API endpoints per client IP."""

    async def dispatch(self, request: Request, call_next) -> Response:  # noqa: ANN001
        path = request.url.path

        # Skip exempt paths
        if path in _EXEMPT_PATHS or any(path.startswith(p) for p in _EXEMPT_PREFIXES):
            return await call_next(request)

        # Only rate-limit specific expensive endpoints
        if not any(path.startswith(p) for p in _RATE_LIMITED_PREFIXES):
            return await call_next(request)

        client_ip = _get_client_ip(request)

        if not _limiter.is_allowed(client_ip):
            raise HTTPException(
                status_code=429,
                detail="Too many requests. Please try again later.",
            )

        return await call_next(request)
