"""Snapshot diff + drift detection for tend.

Read-only on agent source files. All output is written under
``<agent-dir>/.tend/`` — never to SOUL.md, identity.yaml, or memory/.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from agentforge.tend.models import (
    PersonaSnapshot,
    WatchFinding,
    WatchReport,
    watch_report_path,
)

# Voice metrics whose absolute deltas we surface, keyed by metric name.
VOICE_THRESHOLDS = {
    "avg_sentence_length": 3.0,      # words per sentence
    "question_rate": 0.05,           # 5pp absolute
    "exclamation_rate": 0.05,
    "first_person_rate": 0.02,
    "second_person_rate": 0.02,
    "imperative_lead_rate": 0.05,
}


def list_snapshots(agent_dir: Path) -> list[Path]:
    """Return snapshots oldest→newest."""
    snap_dir = agent_dir / ".tend" / "snapshots"
    if not snap_dir.is_dir():
        return []
    return sorted(p for p in snap_dir.glob("*.json") if p.is_file())


def load_snapshot(path: Path) -> PersonaSnapshot:
    return PersonaSnapshot.model_validate(json.loads(path.read_text(encoding="utf-8")))


def _diff_lists(prior: list[str], current: list[str]) -> tuple[list[str], list[str]]:
    p_set = {x.strip().lower(): x for x in prior}
    c_set = {x.strip().lower(): x for x in current}
    added = [c_set[k] for k in c_set if k not in p_set]
    removed = [p_set[k] for k in p_set if k not in c_set]
    return added, removed


def _artifact_findings(prior: PersonaSnapshot, current: PersonaSnapshot) -> list[WatchFinding]:
    """Detect persona-artifact hash changes between two snapshots."""
    out: list[WatchFinding] = []
    p_by_path = {a.path: a for a in prior.artifacts}
    c_by_path = {a.path: a for a in current.artifacts}

    for path, c_art in c_by_path.items():
        p_art = p_by_path.get(path)
        if p_art is None:
            out.append(WatchFinding(
                kind="artifact_added",
                severity="info",
                message=f"new persona artifact: {path}",
                detail=f"sha256={c_art.sha256[:12]}, lines={c_art.line_count}",
            ))
            continue
        if p_art.sha256 != c_art.sha256:
            severity = "warn" if path == "SOUL.md" else "info"
            kind = "soul_changed" if path == "SOUL.md" else "artifact_changed"
            out.append(WatchFinding(
                kind=kind,
                severity=severity,
                message=f"{path} content changed",
                detail=(
                    f"sha256 {p_art.sha256[:12]} → {c_art.sha256[:12]}, "
                    f"lines {p_art.line_count} → {c_art.line_count}"
                ),
            ))
    for path in p_by_path:
        if path not in c_by_path:
            out.append(WatchFinding(
                kind="artifact_removed",
                severity="warn",
                message=f"persona artifact removed: {path}",
            ))
    return out


def _principle_findings(prior: PersonaSnapshot, current: PersonaSnapshot) -> list[WatchFinding]:
    out: list[WatchFinding] = []
    added, removed = _diff_lists(prior.soul_principles, current.soul_principles)
    if added:
        out.append(WatchFinding(
            kind="principles_added",
            severity="info",
            message=f"{len(added)} SOUL principle(s) added",
            detail="\n".join(f"+ {p}" for p in added[:10]),
        ))
    if removed:
        out.append(WatchFinding(
            kind="principles_removed",
            severity="warn",
            message=f"{len(removed)} SOUL principle(s) removed",
            detail="\n".join(f"- {p}" for p in removed[:10]),
        ))
    g_added, g_removed = _diff_lists(prior.soul_guardrails, current.soul_guardrails)
    if g_added:
        out.append(WatchFinding(
            kind="guardrails_added",
            severity="info",
            message=f"{len(g_added)} SOUL guardrail(s) added",
            detail="\n".join(f"+ {g}" for g in g_added),
        ))
    if g_removed:
        out.append(WatchFinding(
            kind="guardrails_removed",
            severity="critical",
            message=f"{len(g_removed)} SOUL guardrail(s) removed",
            detail="\n".join(f"- {g}" for g in g_removed),
        ))
    return out


def _voice_findings(prior: PersonaSnapshot, current: PersonaSnapshot) -> list[WatchFinding]:
    out: list[WatchFinding] = []
    if prior.voice is None or current.voice is None:
        return out
    for metric, threshold in VOICE_THRESHOLDS.items():
        p_val = getattr(prior.voice, metric)
        c_val = getattr(current.voice, metric)
        delta = c_val - p_val
        if abs(delta) >= threshold:
            sign = "+" if delta > 0 else ""
            out.append(WatchFinding(
                kind="voice_shift",
                severity="info",
                message=f"voice metric {metric} shifted",
                detail=f"{p_val:.3f} → {c_val:.3f} ({sign}{delta:.3f})",
            ))
    return out


def _promotion_findings(current: PersonaSnapshot) -> list[WatchFinding]:
    """Memory signals not already covered by SOUL principles/guardrails."""
    if not current.memory_signals:
        return []
    soul_text = " ".join(
        current.soul_principles + current.soul_guardrails
    ).lower()
    candidates: list[str] = []
    for sig in current.memory_signals:
        sig_l = sig.lower()
        # crude containment check: if no 4+ word substring of the signal
        # appears in soul_text, treat it as a candidate.
        words = sig_l.split()
        windowed = [
            " ".join(words[i : i + 4])
            for i in range(0, max(len(words) - 3, 1))
        ]
        if not any(w and w in soul_text for w in windowed):
            candidates.append(sig)
    if not candidates:
        return []
    return [WatchFinding(
        kind="promotion_candidate",
        severity="info",
        message=f"{len(candidates)} memory signal(s) not reflected in SOUL",
        detail="\n".join(f"• {c}" for c in candidates[:10]),
    )]


def watch(agent_dir: Path, compared_at: datetime | None = None) -> WatchReport:
    """Compare the two most recent snapshots and produce a WatchReport.

    Caller is responsible for ensuring at least one snapshot exists; if
    none exist the report is empty with a single 'no_snapshots' finding.
    """
    agent_dir = agent_dir.resolve()
    compared_at = compared_at or datetime.now(timezone.utc)
    snaps = list_snapshots(agent_dir)
    if not snaps:
        return WatchReport(
            agent_name=agent_dir.name,
            compared_at=compared_at,
            prior_snapshot=None,
            current_snapshot="(none)",
            findings=[WatchFinding(
                kind="no_snapshots",
                severity="warn",
                message="no snapshots found — run `tend ingest` first",
            )],
        )
    current = load_snapshot(snaps[-1])
    if len(snaps) == 1:
        return WatchReport(
            agent_name=current.agent_name,
            compared_at=compared_at,
            prior_snapshot=None,
            current_snapshot=str(snaps[-1]),
            findings=[WatchFinding(
                kind="bootstrap",
                severity="info",
                message="first snapshot — nothing to compare against yet",
                detail=f"baseline: {snaps[-1].name}",
            )] + _promotion_findings(current),
        )
    prior = load_snapshot(snaps[-2])
    findings: list[WatchFinding] = []
    findings.extend(_artifact_findings(prior, current))
    findings.extend(_principle_findings(prior, current))
    findings.extend(_voice_findings(prior, current))
    findings.extend(_promotion_findings(current))
    return WatchReport(
        agent_name=current.agent_name,
        compared_at=compared_at,
        prior_snapshot=str(snaps[-2]),
        current_snapshot=str(snaps[-1]),
        findings=findings,
    )


_SEVERITY_ICON = {"info": "·", "warn": "!", "critical": "‼"}


def render_report_markdown(report: WatchReport) -> str:
    lines: list[str] = [
        f"# tend watch — {report.agent_name}",
        "",
        f"- Compared at: {report.compared_at.isoformat(timespec='seconds')}",
        f"- Prior snapshot: `{Path(report.prior_snapshot).name if report.prior_snapshot else '—'}`",
        f"- Current snapshot: `{Path(report.current_snapshot).name}`",
        f"- Findings: {len(report.findings)}",
        "",
    ]
    if not report.findings:
        lines.append("_no findings — nothing changed since the prior snapshot._")
        return "\n".join(lines) + "\n"
    for f in report.findings:
        icon = _SEVERITY_ICON.get(f.severity, "·")
        lines.append(f"## {icon} {f.severity.upper()} — {f.kind}")
        lines.append("")
        lines.append(f.message)
        if f.detail:
            lines.append("")
            lines.append("```")
            lines.append(f.detail)
            lines.append("```")
        lines.append("")
    return "\n".join(lines) + "\n"


def write_report(report: WatchReport, agent_dir: Path) -> Path:
    out = watch_report_path(agent_dir, report.compared_at)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_report_markdown(report), encoding="utf-8")
    return out
