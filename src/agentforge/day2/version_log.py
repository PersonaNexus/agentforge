"""Shared JSONL evolution-log helpers for Tend, Drill, and future day-2+ products.

Each product owns its own ``VersionEntry`` pydantic model (different
fields per product), but the load / annotate / render mechanics are
identical. This module provides those mechanics generically over any
``BaseModel`` subclass.
"""

from __future__ import annotations

import json
from typing import Iterable, TypeVar
from pathlib import Path

from pydantic import BaseModel


E = TypeVar("E", bound=BaseModel)


def load_versions(path: Path, entry_cls: type[E]) -> list[E]:
    """Load a JSONL log into validated entry models. Skips malformed lines silently."""
    if not path.is_file():
        return []
    out: list[E] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(entry_cls.model_validate(json.loads(line)))
        except (json.JSONDecodeError, ValueError):
            continue
    return out


def annotate_latest(path: Path, entry_cls: type[E], note: str) -> E | None:
    """Attach a free-form note to the most recent version entry. Returns the
    updated entry or None if the log is empty."""
    entries = load_versions(path, entry_cls)
    if not entries:
        return None
    entries[-1] = entries[-1].model_copy(update={"note": note})
    path.write_text(
        "\n".join(e.model_dump_json() for e in entries) + "\n",
        encoding="utf-8",
    )
    return entries[-1]


def render_version_log(
    entries: Iterable[BaseModel],
    *,
    title: str,
    empty_text: str,
    row_renderer,
) -> str:
    """Render a versioned log as markdown.

    ``row_renderer(index, entry) -> list[str]`` produces the body lines
    for each entry; the caller controls per-product fields shown.
    """
    rows = list(entries)
    if not rows:
        return empty_text + "\n"
    lines = [f"# {title}", ""]
    for i, entry in enumerate(rows, start=1):
        lines.extend(row_renderer(i, entry))
        lines.append("")
    return "\n".join(lines) + "\n"


def commit_label(git_commit: str | None, git_dirty: bool | None) -> str:
    """Render a short commit label like ``ab12cd34*`` for log output."""
    if not git_commit:
        return "—"
    return git_commit[:8] + ("*" if git_dirty else "")
