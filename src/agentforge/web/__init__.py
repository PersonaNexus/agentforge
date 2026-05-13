"""AgentForge Web UI.

Importing :mod:`agentforge.web` should not require optional web extras.
The FastAPI app factory is loaded lazily so core installs can still import
non-FastAPI web helpers such as auth and rate-limit utilities.
"""

from __future__ import annotations

from typing import Any

__all__ = ["create_app"]


def __getattr__(name: str) -> Any:
    if name == "create_app":
        from agentforge.web.app import create_app

        return create_app
    raise AttributeError(name)
