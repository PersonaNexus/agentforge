"""Deterministic diagnostics over a SkillInventory.

Phase 1.0 surfaces four signal classes, all rule-based:

- **bloat**: SKILL.md body word count above a threshold
- **overlap**: descriptions that share substantial token overlap with
  another skill (Jaccard similarity over token sets)
- **missing_file**: skill folder lacks SKILL.md, or SKILL.md references
  a file path that doesn't exist on disk
- **tool_sprawl**: ``allowed-tools`` list above a threshold, or declared
  tools that don't appear in the body (signals stale entries)

Phase 1.1 will add LLM-judged semantic conflict detection and skill
absorption proposals. Those are kept out of Phase 1.0 to honor the
day-2+ rule: deterministic by default, LLM only on
experimentation/proposal surfaces.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from agentforge.day2.finding_render import render_findings_markdown
from agentforge.drill.models import ScanFinding, ScanReport, SkillInventory


# Defaults — tuneable via CLI flags later. Conservative for Phase 1.0:
# triggers should be obvious, not hair-trigger.
BLOAT_WORD_THRESHOLD = 1500
TOOL_SPRAWL_THRESHOLD = 8
OVERLAP_JACCARD_THRESHOLD = 0.55
DESCRIPTION_MIN_TOKENS = 4  # below this, skip overlap check (noisy)


_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset({
    "the", "a", "an", "and", "or", "but", "of", "for", "to", "in", "on",
    "at", "by", "with", "from", "as", "is", "are", "be", "this", "that",
    "it", "its", "use", "used", "uses", "using", "you", "your", "we", "our",
    "skill", "skills", "agent",
})


def _tokens(text: str) -> set[str]:
    return {t for t in _TOKEN_RE.findall(text.lower()) if t not in _STOPWORDS and len(t) > 2}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def _check_bloat(inventory: SkillInventory, threshold: int) -> list[ScanFinding]:
    findings: list[ScanFinding] = []
    for digest in inventory.skills:
        if not digest.has_skill_md:
            continue
        if digest.body_word_count > threshold:
            findings.append(ScanFinding(
                kind="bloat",
                severity="warn",
                skill=digest.slug,
                message=f"SKILL.md body is {digest.body_word_count} words "
                        f"(threshold: {threshold})",
                detail="Long SKILL.md bodies hurt routing precision; consider "
                       "extracting sub-procedures into instructions/ files.",
            ))
    return findings


def _check_overlap(inventory: SkillInventory, threshold: float) -> list[ScanFinding]:
    findings: list[ScanFinding] = []
    descriptors: list[tuple[str, set[str]]] = []
    for digest in inventory.skills:
        if not digest.has_skill_md:
            continue
        if not digest.description:
            continue
        toks = _tokens(digest.description)
        if len(toks) < DESCRIPTION_MIN_TOKENS:
            continue
        descriptors.append((digest.slug, toks))

    seen: set[tuple[str, str]] = set()
    for i, (slug_a, toks_a) in enumerate(descriptors):
        for slug_b, toks_b in descriptors[i + 1:]:
            score = _jaccard(toks_a, toks_b)
            if score < threshold:
                continue
            key = tuple(sorted([slug_a, slug_b]))
            if key in seen:
                continue
            seen.add(key)
            findings.append(ScanFinding(
                kind="overlap",
                severity="warn",
                skill=None,
                message=f"`{slug_a}` and `{slug_b}` descriptions overlap "
                        f"(jaccard: {score:.2f}, threshold: {threshold:.2f})",
                detail="Two skills with near-duplicate descriptions confuse "
                       "the router; consider absorbing one into the other or "
                       "tightening the descriptions to differentiate scope.",
            ))
    return findings


def _check_missing_files(inventory: SkillInventory) -> list[ScanFinding]:
    findings: list[ScanFinding] = []
    skill_dir = Path(inventory.skill_dir)
    for digest in inventory.skills:
        if not digest.has_skill_md:
            findings.append(ScanFinding(
                kind="missing_file",
                severity="critical",
                skill=digest.slug,
                message="skill folder is missing SKILL.md",
                detail="Without SKILL.md the folder is not a valid skill and "
                       "won't be loaded by Claude Code.",
            ))
            continue
        skill_root = skill_dir / digest.path
        for ref in digest.referenced_files:
            # Skip likely-non-files (URLs, anchors slipped through, looks-like-shell tokens).
            if not ref or "/" not in ref and "." not in ref:
                continue
            if ref.startswith(("http", "#")):
                continue
            target = (skill_root / ref).resolve()
            try:
                target.relative_to(skill_root.resolve())
            except ValueError:
                # Cross-skill references are allowed (Phase 1.1 may flag them);
                # for now we only check refs that resolve inside the skill.
                continue
            if not target.exists():
                findings.append(ScanFinding(
                    kind="broken_reference",
                    severity="warn",
                    skill=digest.slug,
                    message=f"SKILL.md references missing file `{ref}`",
                    detail="The skill body mentions this path in backticks "
                           "or a markdown link but the file isn't present.",
                ))
    return findings


def _check_tool_sprawl(inventory: SkillInventory, threshold: int) -> list[ScanFinding]:
    findings: list[ScanFinding] = []
    for digest in inventory.skills:
        if not digest.has_skill_md:
            continue
        n = len(digest.allowed_tools)
        if n > threshold:
            findings.append(ScanFinding(
                kind="tool_sprawl",
                severity="warn",
                skill=digest.slug,
                message=f"{n} allowed-tools (threshold: {threshold})",
                detail="Long allowed-tools lists weaken the skill's safety "
                       "boundary; trim to what the body actually invokes.",
            ))
            continue
        # Tools declared but not mentioned in the body — likely stale.
        unused = [t for t in digest.allowed_tools if t not in digest.declared_tools_in_body]
        if unused and digest.allowed_tools:
            # Only flag when at least 2 stale tools or >40% of the list.
            ratio = len(unused) / len(digest.allowed_tools)
            if len(unused) >= 2 or ratio > 0.4:
                findings.append(ScanFinding(
                    kind="tool_sprawl",
                    severity="info",
                    skill=digest.slug,
                    message=f"{len(unused)} allowed-tools not referenced in body: "
                            + ", ".join(f"`{t}`" for t in unused[:5])
                            + ("…" if len(unused) > 5 else ""),
                    detail="Tools declared in frontmatter but never mentioned "
                           "in the body are usually stale and can be removed.",
                ))
    return findings


def scan(
    inventory: SkillInventory,
    *,
    bloat_threshold: int = BLOAT_WORD_THRESHOLD,
    tool_threshold: int = TOOL_SPRAWL_THRESHOLD,
    overlap_threshold: float = OVERLAP_JACCARD_THRESHOLD,
    scanned_at: datetime | None = None,
) -> ScanReport:
    """Run all Phase 1.0 deterministic checks over an inventory."""
    scanned_at = scanned_at or datetime.now(timezone.utc)
    findings: list[ScanFinding] = []
    findings.extend(_check_missing_files(inventory))
    findings.extend(_check_bloat(inventory, bloat_threshold))
    findings.extend(_check_overlap(inventory, overlap_threshold))
    findings.extend(_check_tool_sprawl(inventory, tool_threshold))
    return ScanReport(
        skill_dir=inventory.skill_dir,
        scanned_at=scanned_at,
        inventory_captured_at=inventory.captured_at,
        findings=findings,
    )


def render_report_markdown(report: ScanReport) -> str:
    """Render a scan report as human-readable markdown."""
    return render_findings_markdown(
        title=f"drill scan — {report.skill_dir}",
        metadata_lines=[
            f"_scanned: {report.scanned_at.isoformat(timespec='seconds')}_  "
            f"_inventory: {report.inventory_captured_at.isoformat(timespec='seconds')}_",
        ],
        findings=report.findings,
        empty_text="_No issues detected._",
        kind_order=["missing_file", "broken_reference", "bloat", "overlap", "tool_sprawl"],
        scope_attr="skill",
    )


def write_report(report: ScanReport, skill_dir: Path) -> Path:
    """Persist a scan report under <skill-dir>/.drill/."""
    out_dir = skill_dir / ".drill"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = report.scanned_at.strftime("%Y-%m-%dT%H%M%S")
    md_path = out_dir / f"scan-{stamp}.md"
    md_path.write_text(render_report_markdown(report), encoding="utf-8")
    json_path = out_dir / f"scan-{stamp}.json"
    json_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    return md_path
