"""Ingest an agent directory into a PersonaSnapshot.

Reads the artifact zoo a typical PersonaNexus/AgentForge-shaped agent
carries (SOUL.md, identity.yaml, *.personality.json, MEMORY.md, memory/*.md)
and produces a structured snapshot suitable for diffing.

This module is fully deterministic — no LLM calls. Voice fingerprinting,
section parsing, and signal extraction are all rule-based, so two ingests
of an unchanged agent produce identical (modulo timestamp) snapshots.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import yaml

from agentforge.day2.safe_io import FileTooLargeError, read_text_capped
from agentforge.tend.models import (
    ArtifactDigest,
    PersonaSnapshot,
    SoulSection,
    VoiceFingerprint,
)

# Filenames we treat as SOUL-shaped (markdown narrative persona).
SOUL_FILENAMES = ("SOUL.md",)
# Additional persona artifacts we hash and surface but don't deep-parse.
PERSONA_GLOBS = (
    "*.SOUL.md",
    "*.STYLE.md",
    "*.compiled.md",
    "*.personality.json",
    "IDENTITY.md",
    "axiom.yaml",
    "identity.yaml",
    "manifest.yaml",
)
# YAML files we attempt to parse for traits/principles/guardrails.
YAML_FILENAMES = ("identity.yaml", "axiom.yaml")

GUARDRAIL_PATTERNS = (
    re.compile(r"\bnever\b", re.IGNORECASE),
    re.compile(r"\balways\b", re.IGNORECASE),
    re.compile(r"\bdon'?t\b", re.IGNORECASE),
    re.compile(r"\bmust not\b", re.IGNORECASE),
    re.compile(r"\bdo not\b", re.IGNORECASE),
    re.compile(r"\bprivate\b", re.IGNORECASE),
)

PROMOTION_PATTERNS = (
    re.compile(r"\bI should\b", re.IGNORECASE),
    re.compile(r"\bI must\b", re.IGNORECASE),
    re.compile(r"\bI will never\b", re.IGNORECASE),
    re.compile(r"\blesson[: ]", re.IGNORECASE),
    re.compile(r"\blearned\b", re.IGNORECASE),
    re.compile(r"\bnext time\b", re.IGNORECASE),
)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _line_count(path: Path) -> int:
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        return sum(1 for _ in fh)


def _digest(path: Path, agent_dir: Path) -> ArtifactDigest:
    return ArtifactDigest(
        path=str(path.relative_to(agent_dir)),
        size_bytes=path.stat().st_size,
        sha256=_sha256(path),
        line_count=_line_count(path),
    )


def _parse_soul_sections(text: str) -> list[SoulSection]:
    """Split a SOUL.md body into H2 sections."""
    sections: list[SoulSection] = []
    current_heading: str | None = None
    current_body: list[str] = []

    def flush() -> None:
        if current_heading is None:
            return
        body = "\n".join(current_body).strip()
        bullets = [
            ln.lstrip("-* ").strip()
            for ln in current_body
            if ln.lstrip().startswith(("- ", "* "))
        ]
        sections.append(
            SoulSection(heading=current_heading, body=body, bullets=bullets)
        )

    for line in text.splitlines():
        if line.startswith("## "):
            flush()
            current_heading = line[3:].strip()
            current_body = []
        elif current_heading is not None:
            current_body.append(line)
    flush()
    return sections


_MD_INLINE = re.compile(r"\*\*|__|`")
_LETTERS = re.compile(r"[A-Za-z]")
_BOLD = re.compile(r"\*\*([^*]+)\*\*")


def _clean(line: str) -> str:
    """Strip residual markdown markup from a candidate principle line."""
    return _MD_INLINE.sub("", line).strip()


def _looks_like_principle(line: str) -> bool:
    """Filter out junk: too short, too symbol-heavy, or pure label."""
    if len(line) < 12 or len(line) > 240:
        return False
    letters = sum(1 for c in line if _LETTERS.match(c))
    if letters / max(len(line), 1) < 0.55:
        return False
    return True


def _extract_principles(sections: list[SoulSection]) -> list[str]:
    """Pull principle-shaped lines from SOUL sections.

    Combines bold leads and bullets, drops noise (very short labels,
    URL/path-heavy lines), and prefers the longer of two principles when
    one is a prefix of the other (e.g. ``**Foo**`` vs ``Foo for X``).
    """
    raw: list[str] = []
    for sec in sections:
        for line in sec.body.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            for m in _BOLD.finditer(stripped):
                raw.append(_clean(m.group(1)))
        for bullet in sec.bullets:
            raw.append(_clean(bullet))

    raw = [p for p in raw if _looks_like_principle(p)]

    # Prefer the longer of any two principles where one is a prefix of the
    # other (case-insensitive). This collapses "**Demonstrate X**" into
    # "Demonstrate X for any audience level" when both are present.
    raw_sorted = sorted(raw, key=len, reverse=True)
    kept: list[str] = []
    for p in raw_sorted:
        p_l = p.lower()
        if any(k.lower().startswith(p_l) for k in kept):
            continue
        kept.append(p)
    # Restore reading order based on first-seen position in `raw`.
    order = {p: i for i, p in enumerate(raw)}
    kept.sort(key=lambda p: order.get(p, 0))

    seen = set()
    deduped = []
    for p in kept:
        key = p.lower()
        if key not in seen:
            seen.add(key)
            deduped.append(p)
    return deduped


def _extract_guardrails(sections: list[SoulSection]) -> list[str]:
    """Pull guardrail-shaped lines (contain never/always/don't/private)."""
    out: list[str] = []
    for sec in sections:
        if "boundar" in sec.heading.lower() or "guardrail" in sec.heading.lower():
            for bullet in sec.bullets:
                cleaned = _clean(bullet)
                if cleaned:
                    out.append(cleaned)
            continue
        for line in sec.body.splitlines():
            stripped = _clean(line.strip().lstrip("-* "))
            if not stripped or len(stripped) > 240:
                continue
            if any(p.search(stripped) for p in GUARDRAIL_PATTERNS):
                out.append(stripped)
    seen = set()
    deduped = []
    for g in out:
        key = g.lower()
        if key not in seen:
            seen.add(key)
            deduped.append(g)
    return deduped


_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"'])")
_WORD = re.compile(r"\b[\w']+\b")


def _voice_fingerprint(text: str) -> VoiceFingerprint:
    plain = re.sub(r"[*_`#>]", "", text)
    plain = re.sub(r"\[(.*?)\]\(.*?\)", r"\1", plain)
    sentences = [s.strip() for s in _SENT_SPLIT.split(plain) if s.strip()]
    words = _WORD.findall(plain.lower())
    sent_count = max(len(sentences), 1)
    word_count = max(len(words), 1)

    questions = sum(1 for s in sentences if s.endswith("?"))
    exclaims = sum(1 for s in sentences if s.endswith("!"))
    first_person = sum(1 for w in words if w in {"i", "me", "my", "mine", "we", "us", "our"})
    second_person = sum(1 for w in words if w in {"you", "your", "yours"})

    imperative_lead = 0
    common_imperatives = {
        "be", "do", "have", "make", "take", "use", "read", "write", "ask",
        "skip", "remember", "earn", "treat", "keep", "stay", "tell",
    }
    for s in sentences:
        first = re.match(r"\b([A-Za-z']+)\b", s)
        if first and first.group(1).lower() in common_imperatives:
            imperative_lead += 1

    trigrams: Counter[tuple[str, str, str]] = Counter()
    for i in range(len(words) - 2):
        trigrams[(words[i], words[i + 1], words[i + 2])] += 1
    top = [(" ".join(t), c) for t, c in trigrams.most_common(20)]

    return VoiceFingerprint(
        char_count=len(plain),
        word_count=len(words),
        sentence_count=len(sentences),
        avg_sentence_length=word_count / sent_count,
        question_rate=questions / sent_count,
        exclamation_rate=exclaims / sent_count,
        first_person_rate=first_person / word_count,
        second_person_rate=second_person / word_count,
        imperative_lead_rate=imperative_lead / sent_count,
        top_trigrams=top,
    )


def _parse_yaml_persona(path: Path) -> tuple[dict, list[str], list[str]]:
    """Return (personality_dict, principles, guardrails) from a yaml persona."""
    try:
        data = yaml.safe_load(read_text_capped(path)) or {}
    except (yaml.YAMLError, FileTooLargeError):
        return {}, [], []
    if not isinstance(data, dict):
        return {}, [], []

    personality = data.get("personality", {}) or {}
    if not isinstance(personality, dict):
        personality = {}

    principles_raw = data.get("principles", []) or []
    principles: list[str] = []
    if isinstance(principles_raw, list):
        for p in principles_raw:
            if isinstance(p, dict):
                stmt = p.get("statement") or p.get("rule") or p.get("id")
                if stmt:
                    principles.append(str(stmt))
            elif isinstance(p, str):
                principles.append(p)

    guardrails: list[str] = []
    g = data.get("guardrails", {}) or {}
    if isinstance(g, dict):
        for bucket in ("hard", "soft"):
            for entry in g.get(bucket, []) or []:
                if isinstance(entry, dict):
                    rule = entry.get("rule") or entry.get("statement") or entry.get("id")
                    if rule:
                        guardrails.append(str(rule))
                elif isinstance(entry, str):
                    guardrails.append(entry)
    return personality, principles, guardrails


def _scan_memory(memory_dir: Path, days: int = 7) -> list[str]:
    """Return up to ~50 promotion-candidate lines from recent memory files."""
    if not memory_dir.is_dir():
        return []
    files = sorted(
        (p for p in memory_dir.glob("*.md") if p.is_file()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )[:days]
    out: list[str] = []
    for f in files:
        try:
            text = read_text_capped(f)
        except (OSError, FileTooLargeError):
            continue
        for line in text.splitlines():
            stripped = line.strip().lstrip("-*> ").strip()
            if not stripped or len(stripped) > 240:
                continue
            if any(p.search(stripped) for p in PROMOTION_PATTERNS):
                out.append(stripped)
                if len(out) >= 50:
                    return out
    return out


def ingest(agent_dir: Path, captured_at: datetime | None = None) -> PersonaSnapshot:
    """Build a PersonaSnapshot for an agent directory."""
    agent_dir = agent_dir.resolve()
    if not agent_dir.is_dir():
        raise ValueError(f"not a directory: {agent_dir}")
    captured_at = captured_at or datetime.now(timezone.utc)

    notes: list[str] = []
    soul_path = agent_dir / "SOUL.md"
    sections: list[SoulSection] = []
    principles: list[str] = []
    guardrails: list[str] = []
    voice: VoiceFingerprint | None = None
    if soul_path.is_file():
        try:
            soul_text = read_text_capped(soul_path)
        except FileTooLargeError as exc:
            notes.append(f"SOUL.md skipped: {exc}")
            soul_text = ""
        if soul_text:
            sections = _parse_soul_sections(soul_text)
            principles = _extract_principles(sections)
            guardrails = _extract_guardrails(sections)
            voice = _voice_fingerprint(soul_text)
    else:
        notes.append("no SOUL.md found")

    yaml_personality: dict = {}
    yaml_principles: list[str] = []
    yaml_guardrails: list[str] = []
    for fname in YAML_FILENAMES:
        p = agent_dir / fname
        if p.is_file():
            pers, princ, guards = _parse_yaml_persona(p)
            if pers:
                yaml_personality.update(pers)
            yaml_principles.extend(princ)
            yaml_guardrails.extend(guards)

    artifacts: list[ArtifactDigest] = []
    seen_paths: set[Path] = set()
    for fname in SOUL_FILENAMES:
        p = agent_dir / fname
        if p.is_file() and p not in seen_paths:
            artifacts.append(_digest(p, agent_dir))
            seen_paths.add(p)
    for pattern in PERSONA_GLOBS:
        for p in sorted(agent_dir.glob(pattern)):
            if p.is_file() and p not in seen_paths:
                artifacts.append(_digest(p, agent_dir))
                seen_paths.add(p)

    memory_signals = _scan_memory(agent_dir / "memory")

    return PersonaSnapshot(
        agent_dir=str(agent_dir),
        agent_name=agent_dir.name,
        captured_at=captured_at,
        soul_sections=sections,
        soul_principles=principles,
        soul_guardrails=guardrails,
        voice=voice,
        yaml_personality=yaml_personality,
        yaml_principles=yaml_principles,
        yaml_guardrails=yaml_guardrails,
        artifacts=artifacts,
        memory_signals=memory_signals,
        notes=notes,
    )


def write_snapshot(snapshot: PersonaSnapshot, out_path: Path) -> Path:
    """Persist snapshot JSON, creating parent dirs as needed."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(snapshot.model_dump_json(indent=2), encoding="utf-8")
    return out_path
