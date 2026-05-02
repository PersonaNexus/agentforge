"""Pydantic models for tend snapshots and watch findings."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field


class SoulSection(BaseModel):
    """One H2 section of a SOUL.md (or similar) file."""

    heading: str
    body: str
    bullets: list[str] = Field(default_factory=list)


class VoiceFingerprint(BaseModel):
    """Lightweight, deterministic style fingerprint of an agent's prose."""

    char_count: int
    word_count: int
    sentence_count: int
    avg_sentence_length: float
    question_rate: float
    exclamation_rate: float
    first_person_rate: float
    second_person_rate: float
    imperative_lead_rate: float
    top_trigrams: list[tuple[str, int]] = Field(default_factory=list)


class ArtifactDigest(BaseModel):
    """Hash + size summary of a persona artifact file."""

    path: str
    size_bytes: int
    sha256: str
    line_count: int


class PersonaSnapshot(BaseModel):
    """Structured snapshot of an agent's persona at a point in time.

    Produced by ``tend ingest``. Compared by ``tend watch``.
    """

    schema_version: str = "1"
    agent_dir: str
    agent_name: str
    captured_at: datetime
    soul_sections: list[SoulSection] = Field(default_factory=list)
    soul_principles: list[str] = Field(default_factory=list)
    soul_guardrails: list[str] = Field(default_factory=list)
    voice: VoiceFingerprint | None = None
    yaml_personality: dict = Field(default_factory=dict)
    yaml_principles: list[str] = Field(default_factory=list)
    yaml_guardrails: list[str] = Field(default_factory=list)
    artifacts: list[ArtifactDigest] = Field(default_factory=list)
    memory_signals: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class WatchFinding(BaseModel):
    """Single observation produced by ``tend watch``."""

    kind: str  # e.g. "soul_changed", "drift", "promotion_candidate", "artifact_divergence"
    severity: str = "info"  # info | warn | critical
    message: str
    detail: str | None = None


class WatchReport(BaseModel):
    """Output of one ``tend watch`` run."""

    schema_version: str = "1"
    agent_name: str
    compared_at: datetime
    prior_snapshot: str | None = None
    current_snapshot: str
    findings: list[WatchFinding] = Field(default_factory=list)


def snapshot_path(agent_dir: Path, captured_at: datetime) -> Path:
    """Canonical path for a snapshot JSON under <agent>/.tend/snapshots/."""
    stamp = captured_at.strftime("%Y-%m-%dT%H%M%S")
    return agent_dir / ".tend" / "snapshots" / f"{stamp}.json"


def watch_report_path(agent_dir: Path, compared_at: datetime) -> Path:
    stamp = compared_at.strftime("%Y-%m-%d")
    return agent_dir / ".tend" / f"watch-{stamp}.md"
