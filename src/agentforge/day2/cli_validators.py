"""Shared Typer-friendly directory validation for day-2+ CLI surfaces."""

from __future__ import annotations

from pathlib import Path

import typer


def validate_dir(path: Path, entity: str = "directory") -> Path:
    """Resolve and validate a directory argument; raise BadParameter on failure."""
    resolved = path.expanduser().resolve()
    if not resolved.is_dir():
        raise typer.BadParameter(f"{entity} does not exist or is not a directory: {resolved}")
    return resolved
