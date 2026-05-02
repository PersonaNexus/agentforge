"""Lightweight SOUL version log.

Every time ``tend ingest`` runs, ``record_if_changed`` appends a line to
``<agent>/.tend/versions.jsonl`` if the SOUL.md sha has changed since the
prior recorded version. The log is the persona's history: who edited the
SOUL, when, and what shifted.

Read-only on SOUL itself. No revert command in MVP — versions.jsonl is a
ledger, not a version-control system. To roll back, the user uses git.
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field

from agentforge.tend.models import PersonaSnapshot


class VersionEntry(BaseModel):
    schema_version: str = "1"
    recorded_at: datetime
    soul_sha256: str
    soul_line_count: int
    snapshot_path: str
    git_commit: str | None = None
    git_dirty: bool | None = None
    principles_count: int = 0
    guardrails_count: int = 0
    note: str | None = None
    summary: str | None = None  # short delta from prior version


def _versions_path(agent_dir: Path) -> Path:
    return agent_dir / ".tend" / "versions.jsonl"


def _try_rev_parse(cwd: Path) -> str | None:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        ).stdout.strip() or None
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return None


def _git_state(agent_dir: Path) -> tuple[str | None, bool | None]:
    """Return (commit_sha, soul_is_dirty), walking up if the nearest repo
    has no commits yet (e.g. a stray nested .git with empty history).
    """
    commit = _try_rev_parse(agent_dir)
    cwd_for_status = agent_dir
    if commit is None:
        # Walk up parents looking for a repo with commits.
        for parent in agent_dir.parents:
            commit = _try_rev_parse(parent)
            if commit is not None:
                cwd_for_status = parent
                break
    if commit is None:
        return None, None
    soul = agent_dir / "SOUL.md"
    if not soul.is_file():
        return commit, None
    try:
        status = subprocess.run(
            ["git", "status", "--porcelain", "--", str(soul)],
            cwd=cwd_for_status,
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        ).stdout.strip()
        return commit, bool(status)
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return commit, None


def load_versions(agent_dir: Path) -> list[VersionEntry]:
    p = _versions_path(agent_dir)
    if not p.is_file():
        return []
    out: list[VersionEntry] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(VersionEntry.model_validate(json.loads(line)))
        except (json.JSONDecodeError, ValueError):
            continue
    return out


def _summarize_delta(prior: VersionEntry, snapshot: PersonaSnapshot) -> str:
    p_diff = len(snapshot.soul_principles) - prior.principles_count
    g_diff = len(snapshot.soul_guardrails) - prior.guardrails_count
    return (
        f"principles {prior.principles_count}→{len(snapshot.soul_principles)} "
        f"({p_diff:+d}); guardrails {prior.guardrails_count}→"
        f"{len(snapshot.soul_guardrails)} ({g_diff:+d})"
    )


def record_if_changed(
    agent_dir: Path,
    snapshot: PersonaSnapshot,
    snapshot_path: Path,
) -> VersionEntry | None:
    """Append a VersionEntry iff the SOUL sha differs from the latest entry.

    Returns the new entry, or None if SOUL is unchanged (or no SOUL was found).
    """
    soul_artifact = next(
        (a for a in snapshot.artifacts if a.path == "SOUL.md"), None
    )
    if soul_artifact is None:
        return None

    prior = load_versions(agent_dir)
    latest = prior[-1] if prior else None
    if latest is not None and latest.soul_sha256 == soul_artifact.sha256:
        return None  # no change

    git_commit, dirty = _git_state(agent_dir)
    summary = _summarize_delta(latest, snapshot) if latest else "first observation"
    entry = VersionEntry(
        recorded_at=snapshot.captured_at,
        soul_sha256=soul_artifact.sha256,
        soul_line_count=soul_artifact.line_count,
        snapshot_path=str(snapshot_path),
        git_commit=git_commit,
        git_dirty=dirty,
        principles_count=len(snapshot.soul_principles),
        guardrails_count=len(snapshot.soul_guardrails),
        summary=summary,
    )

    p = _versions_path(agent_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(entry.model_dump_json() + "\n")
    return entry


def render_log(entries: list[VersionEntry]) -> str:
    if not entries:
        return "_no recorded SOUL versions_\n"
    lines = ["# tend version log", ""]
    for i, e in enumerate(entries, start=1):
        commit = (e.git_commit[:8] + ("*" if e.git_dirty else "")) if e.git_commit else "—"
        lines.append(
            f"## v{i}  ·  {e.recorded_at.isoformat(timespec='seconds')}  ·  "
            f"sha `{e.soul_sha256[:12]}`"
        )
        lines.append("")
        lines.append(f"- git: `{commit}`")
        lines.append(f"- soul lines: {e.soul_line_count}")
        lines.append(f"- principles: {e.principles_count} · guardrails: {e.guardrails_count}")
        if e.summary:
            lines.append(f"- delta: {e.summary}")
        if e.note:
            lines.append(f"- note: {e.note}")
        lines.append("")
    return "\n".join(lines) + "\n"


def annotate_latest(agent_dir: Path, note: str) -> VersionEntry | None:
    """Attach a free-form note to the most recent version entry."""
    entries = load_versions(agent_dir)
    if not entries:
        return None
    entries[-1] = entries[-1].model_copy(update={"note": note})
    p = _versions_path(agent_dir)
    p.write_text(
        "\n".join(e.model_dump_json() for e in entries) + "\n",
        encoding="utf-8",
    )
    return entries[-1]
