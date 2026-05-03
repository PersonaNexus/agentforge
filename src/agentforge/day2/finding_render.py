"""Shared markdown rendering for finding lists across day-2+ products.

Tend's watch report, Drill's scan report, and Drill's watch report all
share the same shape: a header, some metadata lines, then a list of
findings with severity / kind / scope / message / detail. This module
renders that shape generically.
"""

from __future__ import annotations

from typing import Protocol


class _FindingLike(Protocol):
    kind: str
    severity: str
    message: str

    @property
    def detail(self) -> str | None: ...

    @property
    def scope(self) -> str | None: ...


class SeverityCounts(dict):
    """Count of findings by severity. Ordered: critical → warn → info."""


def count_severities(findings) -> SeverityCounts:
    counts = SeverityCounts({"critical": 0, "warn": 0, "info": 0})
    for f in findings:
        counts[f.severity] = counts.get(f.severity, 0) + 1
    return counts


def render_findings_markdown(
    *,
    title: str,
    metadata_lines: list[str],
    findings,
    empty_text: str = "_No findings._",
    group_by_kind: bool = True,
    kind_order: list[str] | None = None,
    scope_attr: str = "skill",
) -> str:
    """Render a finding list as markdown.

    Args:
        title: H1 title (e.g. ``"drill scan — /path/to/skills"``).
        metadata_lines: short metadata block rendered between title and findings.
        findings: iterable of objects with ``kind``, ``severity``, ``message``,
            ``detail`` (optional), and an attribute named ``scope_attr`` for the
            affected entity (skill slug, agent name, etc.).
        empty_text: markdown to render when there are no findings.
        group_by_kind: when True, group findings by ``kind`` under H2 headings.
        kind_order: preferred ordering for kind groups; remaining kinds are
            appended alphabetically.
        scope_attr: attribute name to read for the per-finding scope.
    """
    items = list(findings)
    counts = count_severities(items)

    lines = [f"# {title}", ""]
    if metadata_lines:
        lines.extend(metadata_lines)
        lines.append("")
    lines.append(
        f"**{len(items)} finding(s)** — "
        f"critical: {counts.get('critical', 0)}, "
        f"warn: {counts.get('warn', 0)}, "
        f"info: {counts.get('info', 0)}"
    )
    lines.append("")

    if not items:
        lines.append(empty_text)
        lines.append("")
        return "\n".join(lines)

    def _scope(f) -> str | None:
        return getattr(f, scope_attr, None)

    def _emit(f, prefix: str = "- ") -> list[str]:
        scope = _scope(f)
        scope_str = f"`{scope}` — " if scope else ""
        out = [f"{prefix}**[{f.severity}]** {scope_str}{f.message}"]
        detail = getattr(f, "detail", None)
        if detail:
            for d in detail.splitlines():
                out.append(f"  - {d}")
        return out

    if not group_by_kind:
        for f in items:
            lines.extend(_emit(f))
        lines.append("")
        return "\n".join(lines)

    by_kind: dict[str, list] = {}
    for f in items:
        by_kind.setdefault(f.kind, []).append(f)

    order = list(kind_order or [])
    for k in sorted(by_kind.keys()):
        if k not in order:
            order.append(k)

    for kind in order:
        group = by_kind.get(kind)
        if not group:
            continue
        lines.append(f"## {kind} ({len(group)})")
        lines.append("")
        for f in group:
            lines.extend(_emit(f))
        lines.append("")
    return "\n".join(lines)
