"""Bearer token authentication middleware for the AgentForge web API.

Configure via:
  - Environment variable: AGENTFORGE_API_TOKEN
  - Config file: ~/.agentforge/config.yaml -> web_api_token

Set AGENTFORGE_API_TOKEN=disabled to explicitly disable auth (local dev).
When no token is configured, all requests are allowed (backwards-compatible).
"""

from __future__ import annotations

import hmac
import os
import logging

from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

logger = logging.getLogger(__name__)

# Paths that never require auth
_PUBLIC_PATHS = frozenset({"/", "/health"})
_PUBLIC_PREFIXES = ("/static/", "/api/docs", "/openapi.json")


def _get_api_token() -> str | None:
    """Resolve the API token from env or config.

    Returns None if no token is configured (auth disabled).
    Returns "disabled" if explicitly opted out.
    """
    env_token = os.environ.get("AGENTFORGE_API_TOKEN", "").strip()
    if env_token:
        return env_token

    # Fall back to config file
    try:
        from agentforge.config import load_config

        config = load_config()
        return getattr(config, "web_api_token", None) or None
    except Exception:
        return None


class BearerAuthMiddleware(BaseHTTPMiddleware):
    """Validates Bearer token on API routes.

    If no token is configured, all requests pass through (opt-in security).
    """

    async def dispatch(self, request: Request, call_next) -> Response:  # noqa: ANN001
        # Skip auth for public paths
        path = request.url.path
        if path in _PUBLIC_PATHS or any(path.startswith(p) for p in _PUBLIC_PREFIXES):
            return await call_next(request)

        # Skip auth for page routes (HTML pages served by the SPA)
        if not path.startswith("/api/"):
            return await call_next(request)

        token = _get_api_token()

        # No token configured or explicitly disabled → allow all
        if not token or token == "disabled":
            return await call_next(request)

        # Validate Authorization header
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

        provided = auth_header[len("Bearer "):]
        if not hmac.compare_digest(provided, token):
            raise HTTPException(status_code=403, detail="Invalid API token")

        return await call_next(request)
