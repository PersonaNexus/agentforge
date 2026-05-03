"""Drill — day-2+ skill maintenance for AgentForge.

Where Tend (PR #24) keeps the *persona* surface healthy over time, Drill
keeps the *capability* surface healthy:

- ``drill ingest`` reads a skill directory (single skill folder or
  ``.claude/skills/``-shaped parent) and produces a structured
  SkillInventory snapshot.
- ``drill scan`` runs deterministic diagnostics over the latest snapshot
  — bloat, descriptive overlap, missing files, tool sprawl.
- ``drill watch`` diffs two snapshots and surfaces evolution: new/removed
  skills, body growth, expanding allowed-tools, materially changed
  descriptions.
- ``drill version`` is a JSONL evolution log mirroring ``tend version``.

Drill never edits skill files. All output goes to ``<skill-dir>/.drill/``.
"""

from agentforge.drill.models import (
    ScanFinding,
    ScanReport,
    SkillDigest,
    SkillInventory,
    WatchFinding,
    WatchReport,
)

__all__ = [
    "ScanFinding",
    "ScanReport",
    "SkillDigest",
    "SkillInventory",
    "WatchFinding",
    "WatchReport",
]
