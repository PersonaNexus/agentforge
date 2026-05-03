"""Ingest a skill directory into a SkillInventory.

A "skill directory" is one of:

- **single**: a folder containing ``SKILL.md`` directly. We treat the
  folder name as the skill slug and ingest just that one skill.
- **parent**: a folder whose immediate children are skill folders
  (``.claude/skills/``-shaped). Each child with a ``SKILL.md`` is one
  skill in the inventory.

This module is deterministic — no LLM calls. Two ingests of an unchanged
skill dir produce identical (modulo timestamps) inventories.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path

from agentforge.day2.frontmatter import split_frontmatter as _split_frontmatter
from agentforge.day2.safe_io import (
    FileTooLargeError,
    read_text_capped,
    walk_files_no_symlinks,
)
from agentforge.drill.models import SkillDigest, SkillInventory


_BACKTICK_REF_RE = re.compile(r"`([A-Za-z0-9_./\-]+\.[A-Za-z0-9]+)`")
_LINK_REF_RE = re.compile(r"\]\(([^)]+)\)")


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _normalize_allowed_tools(value: object) -> list[str]:
    """Frontmatter ``allowed-tools`` may be a list, a comma-string, or absent."""
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str):
        return [t.strip() for t in value.split(",") if t.strip()]
    return [str(value).strip()]


def _extract_referenced_files(body: str) -> list[str]:
    """Extract file paths the SKILL.md references via backticks or markdown links."""
    refs: set[str] = set()
    for m in _BACKTICK_REF_RE.finditer(body):
        refs.add(m.group(1))
    for m in _LINK_REF_RE.finditer(body):
        target = m.group(1).strip()
        # Skip URLs and anchor-only links.
        if target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        refs.add(target.split("#", 1)[0])
    return sorted(refs)


def _detect_declared_tools(body: str, allowed_tools: list[str]) -> list[str]:
    """Of the declared allowed-tools, which actually appear in the body?

    Returns the subset of ``allowed_tools`` whose token (case-insensitive,
    underscores/hyphens normalized) is present in the body. Used by the
    scan stage to flag tool sprawl.
    """
    if not allowed_tools:
        return []
    body_lc = body.lower()
    found: list[str] = []
    for t in allowed_tools:
        token = t.strip().lower().replace("_", "").replace("-", "")
        body_norm = body_lc.replace("_", "").replace("-", "")
        if token and token in body_norm:
            found.append(t)
    return found


def _walk_files(skill_folder: Path) -> tuple[list[str], int, int]:
    """Return (relative file paths excluding SKILL.md, file_count, total_bytes).

    Skips symlinks at every level (security: avoid metadata leakage from
    symlinks pointing outside the skill folder).
    """
    rels: list[str] = []
    total_bytes = 0
    file_count = 0
    for p in walk_files_no_symlinks(skill_folder):
        if p.name.startswith("."):
            continue
        try:
            total_bytes += p.stat().st_size
        except OSError:
            continue
        file_count += 1
        rel = str(p.relative_to(skill_folder))
        if rel != "SKILL.md":
            rels.append(rel)
    return sorted(rels), file_count, total_bytes


def ingest_skill_folder(skill_folder: Path, root: Path) -> SkillDigest:
    """Ingest one skill folder into a SkillDigest."""
    skill_md = skill_folder / "SKILL.md"
    notes: list[str] = []

    if not skill_md.is_file():
        return SkillDigest(
            slug=skill_folder.name,
            path=str(skill_folder.relative_to(root)),
            has_skill_md=False,
            notes=["SKILL.md missing"],
        )

    try:
        raw = read_text_capped(skill_md)
    except FileTooLargeError as exc:
        return SkillDigest(
            slug=skill_folder.name,
            path=str(skill_folder.relative_to(root)),
            has_skill_md=False,
            notes=[f"SKILL.md skipped: {exc}"],
        )
    fm, body, fm_notes = _split_frontmatter(raw)
    notes.extend(fm_notes)

    allowed_tools = _normalize_allowed_tools(fm.get("allowed-tools") or fm.get("allowed_tools"))
    declared = _detect_declared_tools(body, allowed_tools)
    refs = _extract_referenced_files(body)
    supp_files, file_count, total_bytes = _walk_files(skill_folder)

    description = ""
    desc_value = fm.get("description")
    if isinstance(desc_value, str):
        description = desc_value.strip()
    elif desc_value is not None:
        description = str(desc_value).strip()

    word_count = len(body.split())
    body_sha = _sha256_text(body)

    return SkillDigest(
        slug=skill_folder.name,
        path=str(skill_folder.relative_to(root)),
        description=description,
        body_word_count=word_count,
        body_sha256=body_sha,
        file_count=file_count,
        total_bytes=total_bytes,
        allowed_tools=allowed_tools,
        declared_tools_in_body=declared,
        referenced_files=refs,
        supplementary_files=sorted(supp_files),
        frontmatter_keys=sorted(fm.keys()),
        frontmatter={k: _coerce_jsonable(v) for k, v in fm.items()},
        has_skill_md=True,
        notes=notes,
    )


def _coerce_jsonable(v):
    """Coerce frontmatter values into JSON-friendly types for storage."""
    if isinstance(v, (str, int, float, bool)) or v is None:
        return v
    if isinstance(v, list):
        return [_coerce_jsonable(x) for x in v]
    if isinstance(v, dict):
        return {str(k): _coerce_jsonable(val) for k, val in v.items()}
    return str(v)


def detect_layout(skill_dir: Path) -> str:
    """Decide whether this is a 'single' skill folder or a 'parent' directory."""
    if (skill_dir / "SKILL.md").is_file():
        return "single"
    return "parent"


def discover_skill_folders(skill_dir: Path) -> list[Path]:
    """Find all skill folders under ``skill_dir``.

    Returns a sorted list of folder paths. For 'single' layout that's just
    ``[skill_dir]``; for 'parent' layout it's every immediate child with a
    ``SKILL.md`` plus any child directory that fails the SKILL.md check
    (so the scan stage can flag missing-file findings).
    """
    if (skill_dir / "SKILL.md").is_file():
        return [skill_dir]
    out: list[Path] = []
    for child in sorted(skill_dir.iterdir()):
        if not child.is_dir():
            continue
        if child.name.startswith("."):
            continue
        out.append(child)
    return out


def ingest(skill_dir: Path, captured_at: datetime | None = None) -> SkillInventory:
    """Ingest a skill directory into a SkillInventory."""
    skill_dir = Path(skill_dir).expanduser().resolve()
    if not skill_dir.is_dir():
        raise FileNotFoundError(f"skill_dir does not exist or is not a directory: {skill_dir}")

    captured_at = captured_at or datetime.now(timezone.utc)
    layout = detect_layout(skill_dir)
    folders = discover_skill_folders(skill_dir)

    digests: list[SkillDigest] = []
    notes: list[str] = []
    for folder in folders:
        digests.append(ingest_skill_folder(folder, root=skill_dir))

    if layout == "parent" and not digests:
        notes.append("no skill folders found under parent directory")

    return SkillInventory(
        skill_dir=str(skill_dir),
        layout=layout,
        captured_at=captured_at,
        skills=digests,
        total_skills=sum(1 for d in digests if d.has_skill_md),
        notes=notes,
    )
