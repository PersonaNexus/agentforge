"""Pydantic models for drill snapshots, scan findings, and watch reports."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field


class SkillDigest(BaseModel):
    """Structural digest of one skill folder.

    Captures only the deterministic, read-only signals needed for diff +
    diagnostics. No LLM-extracted fields here — those live in Phase 1.1.
    """

    slug: str  # folder name (filesystem-safe)
    path: str  # relative to skill_dir
    description: str = ""  # frontmatter description if present
    body_word_count: int = 0
    body_sha256: str = ""
    file_count: int = 0  # SKILL.md + supplementary files
    total_bytes: int = 0
    allowed_tools: list[str] = Field(default_factory=list)
    declared_tools_in_body: list[str] = Field(default_factory=list)
    referenced_files: list[str] = Field(default_factory=list)  # paths the SKILL.md references
    supplementary_files: list[str] = Field(default_factory=list)  # actual files on disk
    frontmatter_keys: list[str] = Field(default_factory=list)
    frontmatter: dict = Field(default_factory=dict)
    has_skill_md: bool = True
    notes: list[str] = Field(default_factory=list)  # ingest-time anomalies (e.g. unparseable YAML)


class SkillInventory(BaseModel):
    """A point-in-time inventory of every skill under a directory."""

    schema_version: str = "1"
    skill_dir: str  # absolute root we ingested
    layout: str  # "single" (one skill folder) | "parent" (.claude/skills/-shaped)
    captured_at: datetime
    skills: list[SkillDigest] = Field(default_factory=list)
    total_skills: int = 0
    notes: list[str] = Field(default_factory=list)


class ScanFinding(BaseModel):
    """One observation produced by ``drill scan``."""

    kind: str  # "bloat" | "overlap" | "missing_file" | "tool_sprawl" | "broken_reference"
    severity: str = "info"  # info | warn | critical
    skill: str | None = None  # affected skill slug, if scoped
    message: str
    detail: str | None = None


class ScanReport(BaseModel):
    """Output of one ``drill scan`` run."""

    schema_version: str = "1"
    skill_dir: str
    scanned_at: datetime
    inventory_captured_at: datetime
    findings: list[ScanFinding] = Field(default_factory=list)


class WatchFinding(BaseModel):
    """One observation produced by ``drill watch``."""

    kind: str  # "skill_added" | "skill_removed" | "body_grew" | "tools_expanded" | "description_changed"
    severity: str = "info"
    skill: str | None = None
    message: str
    detail: str | None = None


class WatchReport(BaseModel):
    """Output of one ``drill watch`` run (snapshot N-1 vs N)."""

    schema_version: str = "1"
    skill_dir: str
    compared_at: datetime
    prior_snapshot: str | None = None
    current_snapshot: str
    findings: list[WatchFinding] = Field(default_factory=list)


def snapshot_path(skill_dir: Path, captured_at: datetime) -> Path:
    """Canonical path for an inventory JSON under <skill-dir>/.drill/snapshots/."""
    stamp = captured_at.strftime("%Y-%m-%dT%H%M%S")
    return skill_dir / ".drill" / "snapshots" / f"{stamp}.json"


def scan_report_path(skill_dir: Path, scanned_at: datetime) -> Path:
    stamp = scanned_at.strftime("%Y-%m-%dT%H%M%S")
    return skill_dir / ".drill" / f"scan-{stamp}.md"


def watch_report_path(skill_dir: Path, compared_at: datetime) -> Path:
    stamp = compared_at.strftime("%Y-%m-%d")
    return skill_dir / ".drill" / f"watch-{stamp}.md"
