"""Lightweight SOUL version log.

Every time ``tend ingest`` runs, ``record_if_changed`` appends a line to
``<agent>/.tend/versions.jsonl`` if the SOUL.md sha has changed since the
prior recorded version. The log is the persona's history.

Read-only on SOUL itself. No revert command in MVP — versions.jsonl is a
ledger, not a version-control system. To roll back, the user uses git.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from pydantic import BaseModel

from agentforge.day2.vcs import git_state
from agentforge.day2.version_log import (
    annotate_latest as _annotate_latest,
    commit_label,
    load_versions as _load_versions,
    render_version_log,
)
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


def load_versions(agent_dir: Path) -> list[VersionEntry]:
    return _load_versions(_versions_path(agent_dir), VersionEntry)


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
    """Append a VersionEntry iff the SOUL sha differs from the latest entry."""
    soul_artifact = next(
        (a for a in snapshot.artifacts if a.path == "SOUL.md"), None
    )
    if soul_artifact is None:
        return None

    prior = load_versions(agent_dir)
    latest = prior[-1] if prior else None
    if latest is not None and latest.soul_sha256 == soul_artifact.sha256:
        return None

    git_commit, dirty = git_state(agent_dir, dirty_check_path=agent_dir / "SOUL.md")
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


def _row(i: int, e: VersionEntry) -> list[str]:
    return [
        f"## v{i}  ·  {e.recorded_at.isoformat(timespec='seconds')}  ·  "
        f"sha `{e.soul_sha256[:12]}`",
        "",
        f"- git: `{commit_label(e.git_commit, e.git_dirty)}`",
        f"- soul lines: {e.soul_line_count}",
        f"- principles: {e.principles_count} · guardrails: {e.guardrails_count}",
        *([f"- delta: {e.summary}"] if e.summary else []),
        *([f"- note: {e.note}"] if e.note else []),
    ]


def render_log(entries: list[VersionEntry]) -> str:
    return render_version_log(
        entries,
        title="tend version log",
        empty_text="_no recorded SOUL versions_",
        row_renderer=_row,
    )


def annotate_latest(agent_dir: Path, note: str) -> VersionEntry | None:
    return _annotate_latest(_versions_path(agent_dir), VersionEntry, note)
