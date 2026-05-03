"""Git state probes shared by Tend and Drill version logs."""

from __future__ import annotations

import subprocess
from pathlib import Path


_GIT_TIMEOUT_SEC = 2


def try_rev_parse(cwd: Path) -> str | None:
    """Return the HEAD commit sha at ``cwd``, or None if not a git repo."""
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT_SEC,
        ).stdout.strip() or None
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return None


def git_state(target_dir: Path, dirty_check_path: Path | None = None) -> tuple[str | None, bool | None]:
    """Return (HEAD commit, is_dirty) for ``target_dir``.

    Walks parent directories looking for a repo if ``target_dir`` itself
    isn't tracked (e.g. nested .git with empty history). ``dirty_check_path``
    scopes the dirty check to a specific file/dir; defaults to target_dir.
    """
    commit = try_rev_parse(target_dir)
    cwd_for_status = target_dir
    if commit is None:
        for parent in target_dir.parents:
            commit = try_rev_parse(parent)
            if commit is not None:
                cwd_for_status = parent
                break
    if commit is None:
        return None, None

    check_path = dirty_check_path or target_dir
    if dirty_check_path is not None and not Path(dirty_check_path).exists():
        return commit, None
    try:
        status = subprocess.run(
            ["git", "status", "--porcelain", "--", str(check_path)],
            cwd=cwd_for_status,
            check=True,
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT_SEC,
        ).stdout.strip()
        return commit, bool(status)
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return commit, None
