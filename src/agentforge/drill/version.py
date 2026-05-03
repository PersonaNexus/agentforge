"""Lightweight skill-inventory version log.

Every time ``drill ingest`` runs, ``record_if_changed`` appends a line
to ``<skill-dir>/.drill/versions.jsonl`` if the inventory's content
fingerprint has changed since the prior recorded version.

The fingerprint is the sorted concatenation of every skill's
``body_sha256`` — so a skill body edit, addition, or removal all
produce a new fingerprint, while a no-op re-ingest produces no new
entry.

Mirrors ``tend version`` in shape and intent: an append-only ledger,
not a VCS. Roll back via git on the underlying skill files.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel

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


def _git_state(skill_dir: Path) -> tuple[str | None, bool | None]:
    """Return (commit_sha, skill_dir_is_dirty)."""
    commit = _try_rev_parse(skill_dir)
    cwd_for_status = skill_dir
    if commit is None:
        for parent in skill_dir.parents:
            commit = _try_rev_parse(parent)
            if commit is not None:
                cwd_for_status = parent
                break
    if commit is None:
        return None, None
    try:
        status = subprocess.run(
            ["git", "status", "--porcelain", "--", str(skill_dir)],
            cwd=cwd_for_status,
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        ).stdout.strip()
        return commit, bool(status)
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return commit, None


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
    p = _versions_path(skill_dir)
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

    git_commit, dirty = _git_state(skill_dir)
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


def render_log(entries: list[VersionEntry]) -> str:
    if not entries:
        return "_no recorded skill versions_\n"
    lines = ["# drill version log", ""]
    for i, e in enumerate(entries, start=1):
        commit = (e.git_commit[:8] + ("*" if e.git_dirty else "")) if e.git_commit else "—"
        lines.append(
            f"## v{i}  ·  {e.recorded_at.isoformat(timespec='seconds')}  ·  "
            f"fp `{e.inventory_fingerprint[:12]}`"
        )
        lines.append("")
        lines.append(f"- git: `{commit}`")
        lines.append(f"- skills: {e.skill_count} · words: {e.total_words}")
        if e.summary:
            lines.append(f"- delta: {e.summary}")
        if e.note:
            lines.append(f"- note: {e.note}")
        lines.append("")
    return "\n".join(lines) + "\n"


def annotate_latest(skill_dir: Path, note: str) -> VersionEntry | None:
    """Attach a free-form note to the most recent version entry."""
    entries = load_versions(skill_dir)
    if not entries:
        return None
    entries[-1] = entries[-1].model_copy(update={"note": note})
    p = _versions_path(skill_dir)
    p.write_text(
        "\n".join(e.model_dump_json() for e in entries) + "\n",
        encoding="utf-8",
    )
    return entries[-1]
