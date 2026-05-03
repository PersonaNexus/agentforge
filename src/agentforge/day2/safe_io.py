"""File-size guards and symlink-aware iteration for day-2+ ingest paths.

Prevents two minor abuse vectors flagged in the day-2+ security pass:

- A skill folder with a multi-GB SKILL.md OOMs the process when read
  whole-file with ``read_text()``. We cap reads at ``MAX_INGEST_BYTES``
  and raise rather than silently truncating.
- A skill folder containing symlinks (e.g. to ``/etc/passwd``) leaks
  metadata into snapshots. ``walk_files_no_symlinks`` skips them.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator


# 5 MB. Real SKILL.md / SOUL.md are kilobytes; anything past this is an
# attack or a mistake. Configurable by callers if they need a different cap.
DEFAULT_MAX_INGEST_BYTES = 5 * 1024 * 1024


class FileTooLargeError(ValueError):
    """Raised when an ingested file exceeds the configured size cap."""


def read_text_capped(
    path: Path,
    *,
    max_bytes: int = DEFAULT_MAX_INGEST_BYTES,
    encoding: str = "utf-8",
    errors: str = "replace",
) -> str:
    """Read text from ``path`` with a hard size cap.

    Raises ``FileTooLargeError`` when the file exceeds ``max_bytes``.
    """
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise FileNotFoundError(f"cannot stat {path}: {exc}") from exc
    if size > max_bytes:
        raise FileTooLargeError(
            f"{path} is {size} bytes; ingest cap is {max_bytes} bytes"
        )
    return path.read_text(encoding=encoding, errors=errors)


def walk_files_no_symlinks(root: Path) -> Iterator[Path]:
    """Yield regular files under ``root``, skipping symlinks at every level.

    Uses an explicit stack so we can refuse to descend into symlinked
    directories (which ``Path.rglob`` would still enter on traversal).
    """
    stack: list[Path] = [root]
    while stack:
        current = stack.pop()
        try:
            children = sorted(current.iterdir())
        except OSError:
            continue
        for p in children:
            if p.is_symlink():
                continue
            if p.is_dir():
                stack.append(p)
            elif p.is_file():
                yield p
