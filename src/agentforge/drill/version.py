"""Lightweight skill-inventory version log.

Every time ``drill ingest`` runs, ``record_if_changed`` appends a line
to ``<skill-dir>/.drill/versions.jsonl`` if the inventory's content
fingerprint has changed since the prior recorded version. The
fingerprint is the sorted concat of every skill's ``body_sha256`` —
edits, additions, and removals all change it.

Mirrors ``tend version`` in shape and intent: an append-only ledger,
not a VCS. Roll back via git on the underlying skill files.
"""

from __future__ import annotations

import hashlib
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
from agentforge.drill.models import SkillInventory


class VersionEntry(BaseModel):
    schema_version: str = "1"
    recorded_at: datetime
    inventory_fingerprint: str  # sha256 over sorted (slug, body_sha) pairs
    snapshot_path: str
    git_commit: str | None = None
    git_dirty: bool | None = None
    skill_count: int = 0
    total_words: int = 0
    note: str | None = None
    summary: str | None = None  # short delta from prior version


def _versions_path(skill_dir: Path) -> Path:
    return skill_dir / ".drill" / "versions.jsonl"


def fingerprint(inventory: SkillInventory) -> str:
    """Stable content hash over the inventory.

    Two inventories with the same set of (slug, body_sha256) pairs share
    a fingerprint regardless of ordering or capture timestamp.
    """
    pairs = sorted(
        (d.slug, d.body_sha256) for d in inventory.skills if d.has_skill_md
    )
    h = hashlib.sha256()
    for slug, sha in pairs:
        h.update(slug.encode("utf-8"))
        h.update(b"\x00")
        h.update(sha.encode("utf-8"))
        h.update(b"\n")
    return h.hexdigest()


def load_versions(skill_dir: Path) -> list[VersionEntry]:
    return _load_versions(_versions_path(skill_dir), VersionEntry)


def _summarize_delta(prior: VersionEntry, inventory: SkillInventory) -> str:
    new_count = sum(1 for d in inventory.skills if d.has_skill_md)
    new_words = sum(d.body_word_count for d in inventory.skills)
    c_diff = new_count - prior.skill_count
    w_diff = new_words - prior.total_words
    return (
        f"skills {prior.skill_count}→{new_count} ({c_diff:+d}); "
        f"words {prior.total_words}→{new_words} ({w_diff:+d})"
    )


def record_if_changed(
    skill_dir: Path,
    inventory: SkillInventory,
    snapshot_path: Path,
) -> VersionEntry | None:
    """Append a VersionEntry iff the inventory fingerprint changed."""
    fp = fingerprint(inventory)
    if not fp:
        return None  # no skills with bodies — nothing to version
    prior = load_versions(skill_dir)
    latest = prior[-1] if prior else None
    if latest is not None and latest.inventory_fingerprint == fp:
        return None

    git_commit, dirty = git_state(skill_dir)
    summary = _summarize_delta(latest, inventory) if latest else "first observation"
    entry = VersionEntry(
        recorded_at=inventory.captured_at,
        inventory_fingerprint=fp,
        snapshot_path=str(snapshot_path),
        git_commit=git_commit,
        git_dirty=dirty,
        skill_count=sum(1 for d in inventory.skills if d.has_skill_md),
        total_words=sum(d.body_word_count for d in inventory.skills),
        summary=summary,
    )

    p = _versions_path(skill_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(entry.model_dump_json() + "\n")
    return entry


def _row(i: int, e: VersionEntry) -> list[str]:
    return [
        f"## v{i}  ·  {e.recorded_at.isoformat(timespec='seconds')}  ·  "
        f"fp `{e.inventory_fingerprint[:12]}`",
        "",
        f"- git: `{commit_label(e.git_commit, e.git_dirty)}`",
        f"- skills: {e.skill_count} · words: {e.total_words}",
        *([f"- delta: {e.summary}"] if e.summary else []),
        *([f"- note: {e.note}"] if e.note else []),
    ]


def render_log(entries: list[VersionEntry]) -> str:
    return render_version_log(
        entries,
        title="drill version log",
        empty_text="_no recorded skill versions_",
        row_renderer=_row,
    )


def annotate_latest(skill_dir: Path, note: str) -> VersionEntry | None:
    return _annotate_latest(_versions_path(skill_dir), VersionEntry, note)
