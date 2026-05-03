"""Gap analysis: agent SkillInventory ↔ market SkillLandscape.

Deterministic, no LLM. We use the same name normalization as
Department's clusterer so an agent skill called "PostgreSQL" matches a
corpus mention of "Postgres". Output flags three classes of skill:

- **market_only** — appears in N+ corpus roles but not in the agent
  (the gap to close).
- **agent_only** — agent has it, no corpus role mentions it. Could be
  unique value, could be stale; flag for human review.
- **shared** — agent has it AND ≥1 corpus role mentions it.

Plus a coverage score: of corpus skills appearing in
≥``coverage_role_threshold`` roles OR marked importance ``required``,
what fraction does the agent cover?
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from agentforge.day2.finding_render import render_findings_markdown
from agentforge.department.cluster import _normalize

if TYPE_CHECKING:
    from agentforge.department.cluster import SkillLandscape
    from agentforge.drill.models import SkillInventory


# Skills appearing in ≥ this many corpus roles are treated as
# "load-bearing" market demand for coverage scoring purposes.
DEFAULT_COVERAGE_ROLE_THRESHOLD = 2


class GapSkill(BaseModel):
    """One skill on either side of the agent ↔ market boundary."""

    canonical_name: str
    side: str  # "market_only" | "agent_only" | "shared"
    severity: str = "info"
    role_count: int = 0
    role_share: float = 0.0
    importance_max: str | None = None
    in_agent_skills: list[str] = Field(default_factory=list)
    detail: str | None = None

    @property
    def kind(self) -> str:
        return self.side

    @property
    def message(self) -> str:
        if self.side == "market_only":
            return (
                f"`{self.canonical_name}` — demanded by {self.role_count} "
                f"corpus role(s) ({self.role_share:.0%}); agent has none"
            )
        if self.side == "agent_only":
            agents = ", ".join(f"`{s}`" for s in self.in_agent_skills) or "—"
            return f"`{self.canonical_name}` — present in agent ({agents}); no corpus role uses it"
        agents = ", ".join(f"`{s}`" for s in self.in_agent_skills) or "agent"
        return (
            f"`{self.canonical_name}` — covered "
            f"({self.role_count} corpus role(s) · {agents})"
        )

    @property
    def skill(self) -> str | None:
        # finding_render expects a per-row scope attribute; gap rows are
        # already scoped via canonical_name in their message.
        return None


class GapReport(BaseModel):
    """Output of ``market gap`` — agent vs corpus comparison."""

    schema_version: str = "1"
    corpus_root: str
    agent_skill_dir: str
    generated_at: datetime
    coverage_score: float  # 0..1, fraction of load-bearing market skills covered
    coverage_role_threshold: int = DEFAULT_COVERAGE_ROLE_THRESHOLD
    market_only: list[GapSkill] = Field(default_factory=list)
    agent_only: list[GapSkill] = Field(default_factory=list)
    shared: list[GapSkill] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    @property
    def findings(self) -> list[GapSkill]:
        """Flat list for finding_render — order: market_only → agent_only → shared."""
        return [*self.market_only, *self.agent_only, *self.shared]


def _agent_skill_keys(inventory: "SkillInventory") -> dict[str, list[str]]:
    """Map normalized skill name → list of agent skill slugs that have it.

    Each agent skill contributes multiple keys: its slug, any frontmatter
    ``name`` field, and short clauses from the description (so a skill
    ``ship-pr`` whose description is "Open a pull request..." picks up the
    ``pull request`` market term too).
    """
    out: dict[str, list[str]] = {}
    for digest in inventory.skills:
        if not digest.has_skill_md:
            continue
        candidates: list[str] = [digest.slug]
        fm = digest.frontmatter if isinstance(digest.frontmatter, dict) else {}
        if isinstance(fm.get("name"), str):
            candidates.append(fm["name"])
        if digest.description:
            for chunk in digest.description.replace(";", ".").split("."):
                chunk = chunk.strip()
                if 0 < len(chunk) < 80:
                    candidates.append(chunk)
        for cand in candidates:
            key = _normalize(cand)
            if not key:
                continue
            slugs = out.setdefault(key, [])
            if digest.slug not in slugs:
                slugs.append(digest.slug)
    return out


def _slug_keys(inventory: "SkillInventory") -> dict[str, str]:
    """Map normalized slug → original slug. Used to find truly agent-only
    skills (the slug itself never appearing in the market landscape)."""
    out: dict[str, str] = {}
    for digest in inventory.skills:
        if not digest.has_skill_md:
            continue
        out[_normalize(digest.slug)] = digest.slug
    return out


def _severity_for_market_gap(role_count: int, importance_max: str | None) -> str:
    if importance_max == "required" and role_count >= 3:
        return "critical"
    if role_count >= 3:
        return "warn"
    return "info"


def compute_gap(
    landscape: "SkillLandscape",
    inventory: "SkillInventory",
    *,
    coverage_role_threshold: int = DEFAULT_COVERAGE_ROLE_THRESHOLD,
    corpus_root: str | None = None,
) -> GapReport:
    """Compare a market SkillLandscape to an agent SkillInventory."""
    agent_keys = _agent_skill_keys(inventory)
    slug_keys = _slug_keys(inventory)

    market_only: list[GapSkill] = []
    shared: list[GapSkill] = []
    matched_agent_slugs: set[str] = set()

    total_roles = landscape.role_count or 1
    market_normalized_names: set[str] = {
        _normalize(c.canonical_name) for c in landscape.clusters
    }

    for cluster in landscape.clusters:
        norm = _normalize(cluster.canonical_name)
        agent_hits = agent_keys.get(norm, [])
        if agent_hits:
            matched_agent_slugs.update(agent_hits)
            shared.append(GapSkill(
                canonical_name=cluster.canonical_name,
                side="shared",
                severity="info",
                role_count=cluster.role_count,
                role_share=cluster.role_count / total_roles,
                importance_max=cluster.importance_max,
                in_agent_skills=list(agent_hits),
            ))
        else:
            market_only.append(GapSkill(
                canonical_name=cluster.canonical_name,
                side="market_only",
                severity=_severity_for_market_gap(cluster.role_count, cluster.importance_max),
                role_count=cluster.role_count,
                role_share=cluster.role_count / total_roles,
                importance_max=cluster.importance_max,
            ))

    # agent_only: skills whose slug never matched a market cluster, AND whose
    # slug doesn't substring-match any market cluster name (avoids double-
    # reporting a fuzzy-but-already-shared skill).
    agent_only: list[GapSkill] = []
    for norm_slug, original_slug in slug_keys.items():
        if original_slug in matched_agent_slugs:
            continue
        if any(norm_slug in m for m in market_normalized_names):
            continue
        if any(m and m in norm_slug for m in market_normalized_names if m):
            continue
        agent_only.append(GapSkill(
            canonical_name=original_slug.replace("-", " "),
            side="agent_only",
            severity="info",
            role_count=0,
            role_share=0.0,
            importance_max=None,
            in_agent_skills=[original_slug],
        ))

    # Coverage score: load-bearing market skills covered.
    load_bearing = [
        c for c in landscape.clusters
        if c.role_count >= coverage_role_threshold or c.importance_max == "required"
    ]
    covered = [
        c for c in load_bearing
        if _normalize(c.canonical_name) in agent_keys
    ]
    coverage_score = (len(covered) / len(load_bearing)) if load_bearing else 1.0

    # Stable sort — most-impactful gaps first.
    market_only.sort(key=lambda g: (-g.role_count, g.canonical_name.lower()))
    agent_only.sort(key=lambda g: g.canonical_name.lower())
    shared.sort(key=lambda g: (-g.role_count, g.canonical_name.lower()))

    notes: list[str] = []
    if not landscape.clusters:
        notes.append("market landscape is empty — gap analysis trivially full coverage")

    return GapReport(
        corpus_root=corpus_root or "",
        agent_skill_dir=inventory.skill_dir,
        generated_at=datetime.now(timezone.utc),
        coverage_score=round(coverage_score, 3),
        coverage_role_threshold=coverage_role_threshold,
        market_only=market_only,
        agent_only=agent_only,
        shared=shared,
        notes=notes,
    )


def render_gap_markdown(report: GapReport) -> str:
    """Render a GapReport as readable markdown."""
    pct = int(round(report.coverage_score * 100))
    return render_findings_markdown(
        title=f"market gap — {report.agent_skill_dir} vs {report.corpus_root or '(corpus)'}",
        metadata_lines=[
            f"_generated: {report.generated_at.isoformat(timespec='seconds')}_",
            "",
            f"**Coverage:** {pct}% of load-bearing market skills "
            f"(threshold: ≥{report.coverage_role_threshold} roles or importance=required)",
            "",
            f"- market_only: {len(report.market_only)}  |  "
            f"agent_only: {len(report.agent_only)}  |  "
            f"shared: {len(report.shared)}",
        ],
        findings=report.findings,
        empty_text="_No skills compared._",
        kind_order=["market_only", "agent_only", "shared"],
        scope_attr="skill",
    )


def write_gap_report(report: GapReport, output_dir: Path) -> tuple[Path, Path]:
    output_dir = Path(output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    md_path = output_dir / "market-gap.md"
    md_path.write_text(render_gap_markdown(report), encoding="utf-8")
    json_path = output_dir / "market-gap.json"
    json_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    return md_path, json_path
