"""Diff two SkillInventory snapshots into a WatchReport.

Phase 1.0 watch surfaces five evolution signals between consecutive
snapshots:

- **skill_added** / **skill_removed** — roster changes
- **body_grew** — SKILL.md word count grew by more than ``GROW_RATIO``
- **tools_expanded** — ``allowed-tools`` gained entries
- **description_changed** — description string differs (frontmatter
  edits to the routing surface)

The diff is deterministic and slug-keyed.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from agentforge.drill.models import SkillInventory, WatchFinding, WatchReport


GROW_RATIO = 0.25  # body word count growth that triggers a finding
DESC_TRIVIAL_LEN = 20  # below this, treat any change as material


def list_snapshots(skill_dir: Path) -> list[Path]:
    """Sorted oldest→newest snapshot files under <skill-dir>/.drill/snapshots/."""
    snap_dir = skill_dir / ".drill" / "snapshots"
    if not snap_dir.is_dir():
        return []
    return sorted(snap_dir.glob("*.json"))


def load_snapshot(path: Path) -> SkillInventory:
    """Load a SkillInventory from a snapshot JSON path."""
    return SkillInventory.model_validate(json.loads(path.read_text(encoding="utf-8")))


def _index(inventory: SkillInventory) -> dict[str, "object"]:
    return {d.slug: d for d in inventory.skills}


def _roster_findings(prior: SkillInventory, current: SkillInventory) -> list[WatchFinding]:
    p = _index(prior)
    c = _index(current)
    findings: list[WatchFinding] = []
    for slug in sorted(c.keys() - p.keys()):
        findings.append(WatchFinding(
            kind="skill_added",
            severity="info",
            skill=slug,
            message=f"new skill `{slug}` added since prior snapshot",
        ))
    for slug in sorted(p.keys() - c.keys()):
        findings.append(WatchFinding(
            kind="skill_removed",
            severity="warn",
            skill=slug,
            message=f"skill `{slug}` removed since prior snapshot",
        ))
    return findings


def _per_skill_findings(prior: SkillInventory, current: SkillInventory) -> list[WatchFinding]:
    p = _index(prior)
    c = _index(current)
    findings: list[WatchFinding] = []
    for slug in sorted(p.keys() & c.keys()):
        old = p[slug]
        new = c[slug]
        if not old.has_skill_md or not new.has_skill_md:
            continue
        # Body growth.
        if old.body_word_count > 0:
            ratio = (new.body_word_count - old.body_word_count) / old.body_word_count
            if ratio >= GROW_RATIO:
                findings.append(WatchFinding(
                    kind="body_grew",
                    severity="warn" if ratio >= 0.5 else "info",
                    skill=slug,
                    message=f"`{slug}` SKILL.md grew {old.body_word_count} → "
                            f"{new.body_word_count} words ({ratio:+.0%})",
                    detail="Watch for scope creep in long-running skills; "
                           "extract sub-procedures into instructions/ files.",
                ))
        # Tool surface expansion.
        old_tools = set(old.allowed_tools)
        new_tools = set(new.allowed_tools)
        added_tools = sorted(new_tools - old_tools)
        if added_tools:
            findings.append(WatchFinding(
                kind="tools_expanded",
                severity="warn",
                skill=slug,
                message=f"`{slug}` allowed-tools expanded by "
                        + ", ".join(f"`{t}`" for t in added_tools),
                detail="New tools widen the safety surface; confirm each is "
                       "actually needed by the skill body.",
            ))
        # Description churn.
        if old.description != new.description:
            longer = max(len(old.description), len(new.description))
            severity = "info" if longer < DESC_TRIVIAL_LEN else "warn"
            findings.append(WatchFinding(
                kind="description_changed",
                severity=severity,
                skill=slug,
                message=f"`{slug}` description changed",
                detail=f"before: {old.description!r}\nafter: {new.description!r}",
            ))
    return findings


def watch(
    skill_dir: Path,
    prior_path: Path | None = None,
    current_path: Path | None = None,
    compared_at: datetime | None = None,
) -> WatchReport:
    """Compare the two most recent snapshots (or explicit ones) under skill_dir."""
    skill_dir = Path(skill_dir).expanduser().resolve()
    compared_at = compared_at or datetime.now(timezone.utc)

    if current_path is None or prior_path is None:
        snaps = list_snapshots(skill_dir)
        if len(snaps) < 2:
            return WatchReport(
                skill_dir=str(skill_dir),
                compared_at=compared_at,
                prior_snapshot=str(snaps[0]) if snaps else None,
                current_snapshot=str(snaps[-1]) if snaps else "",
                findings=[],
            )
        prior_path = prior_path or snaps[-2]
        current_path = current_path or snaps[-1]

    prior = load_snapshot(Path(prior_path))
    current = load_snapshot(Path(current_path))

    findings: list[WatchFinding] = []
    findings.extend(_roster_findings(prior, current))
    findings.extend(_per_skill_findings(prior, current))

    return WatchReport(
        skill_dir=str(skill_dir),
        compared_at=compared_at,
        prior_snapshot=str(prior_path),
        current_snapshot=str(current_path),
        findings=findings,
    )


def render_report_markdown(report: WatchReport) -> str:
    lines = [
        f"# drill watch — {report.skill_dir}",
        "",
        f"_compared: {report.compared_at.isoformat(timespec='seconds')}_",
        "",
        f"- prior:   `{report.prior_snapshot or '(none)'}`",
        f"- current: `{report.current_snapshot}`",
        "",
        f"**{len(report.findings)} finding(s)**",
        "",
    ]
    if not report.findings:
        lines.append("_No evolution detected._\n")
        return "\n".join(lines)
    for f in report.findings:
        scope = f"`{f.skill}` — " if f.skill else ""
        lines.append(f"- **[{f.severity}]** {scope}{f.message}")
        if f.detail:
            for d in f.detail.splitlines():
                lines.append(f"  - {d}")
    lines.append("")
    return "\n".join(lines)


def write_report(report: WatchReport, skill_dir: Path) -> Path:
    out_dir = skill_dir / ".drill"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = report.compared_at.strftime("%Y-%m-%d")
    path = out_dir / f"watch-{stamp}.md"
    path.write_text(render_report_markdown(report), encoding="utf-8")
    return path
