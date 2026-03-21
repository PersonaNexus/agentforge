"""Shared utility functions for AgentForge."""

from __future__ import annotations

import os
import re
from pathlib import Path

# Pre-compiled patterns for slug generation
_RE_MULTI_HYPHEN = re.compile(r"-+")
_RE_LEADING_NON_ALNUM = re.compile(r"^[^a-z0-9]+")


def safe_filename(name: str) -> str:
    """Sanitize a string for use as a filename, preventing path traversal.

    Strips path separators, .., and non-alphanumeric characters except
    hyphens, underscores, and dots. Returns a safe, filesystem-friendly string.
    """
    # Remove path traversal components
    name = name.replace("..", "").replace("/", "").replace("\\", "")
    # Keep only alphanumeric, hyphens, underscores, dots
    name = re.sub(r"[^a-zA-Z0-9_\-.]", "_", name)
    # Collapse multiple underscores
    name = re.sub(r"_+", "_", name).strip("_")
    # Fallback if empty
    return name or "unnamed_agent"


def make_skill_slug(title: str, *, strip_leading: bool = False, max_len: int = 64) -> str:
    """Derive a skill slug from a role title.

    Produces lowercase-hyphenated names like 'senior-data-engineer'.

    Args:
        title: The role title to slugify.
        strip_leading: If True, strip leading non-alphanumeric characters
                       (required for ClawHub ^[a-z0-9] format).
        max_len: Maximum slug length (default 64 per spec).
    """
    raw = safe_filename(title).lower().replace("_", "-")
    raw = _RE_MULTI_HYPHEN.sub("-", raw).strip("-")
    if strip_leading:
        raw = _RE_LEADING_NON_ALNUM.sub("", raw)
    if len(raw) > max_len:
        raw = raw[:max_len].rstrip("-")
    return raw or "generated-skill"


def truncate_description(text: str, max_len: int = 200) -> str:
    """Truncate a description string with ellipsis if needed."""
    if len(text) > max_len:
        return text[:max_len - 3] + "..."
    return text


def safe_output_path(output_dir: Path, filename: str) -> Path:
    """Build a safe output path, ensuring it stays within output_dir."""
    safe_name = safe_filename(filename)
    target = (output_dir / safe_name).resolve()
    output_resolved = output_dir.resolve()
    if not str(target).startswith(str(output_resolved)):
        raise ValueError(f"Path traversal detected: {filename!r} escapes {output_dir}")
    return target


def safe_rel_path(base_dir: Path, rel_path: str) -> Path:
    """Resolve a relative path safely within base_dir, preventing path traversal.

    Raises ValueError if the resolved path escapes base_dir.
    """
    # Sanitize each component of the relative path
    parts = Path(rel_path).parts
    clean_parts = [safe_filename(p) for p in parts]
    target = (base_dir / Path(*clean_parts)).resolve()
    base_resolved = base_dir.resolve()
    if not str(target).startswith(str(base_resolved) + os.sep) and target != base_resolved:
        raise ValueError(f"Path traversal detected: {rel_path!r} escapes {base_dir}")
    return target
