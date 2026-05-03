"""Compute and render aggregate JD-corpus trends.

Deterministic — no LLM. Shares the per-JD extraction step with
Department (``agentforge.department.synthesize.extract_corpus``) and
the cluster step (``cluster_skills``) so a corpus that's already been
analyzed by Department reuses its cached extractions.

The recency split is opt-in: it only fires when frontmatter carries a
``date:`` field on enough JDs to make a meaningful before/after.
"""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, TYPE_CHECKING

from agentforge.corpus import Corpus, JDEntry, load_corpus
from agentforge.day2.cli_validators import validate_dir
from agentforge.department.cluster import SkillLandscape, cluster_skills
from agentforge.department.synthesize import extract_corpus
from agentforge.market.models import (
    CategoryBreakdown,
    DomainBreakdown,
    RecencyBucket,
    RecencySignal,
    SeniorityBreakdown,
    SkillTrend,
    TrendsReport,
)

if TYPE_CHECKING:
    from agentforge.models.extracted_skills import ExtractionResult

ExtractorFn = Callable[[JDEntry], "ExtractionResult"]

DEFAULT_RECENCY_WINDOW_DAYS = 90
MIN_RECENCY_BUCKET_SIZE = 2


def _to_skill_trends(landscape: SkillLandscape) -> list[SkillTrend]:
    """Convert clustered landscape into market-shaped SkillTrend rows."""
    total = landscape.role_count or 1
    out: list[SkillTrend] = []
    for c in landscape.clusters:
        # importance_distribution is best-effort; the cluster only tracks max,
        # so we leave the dist empty here. (Phase 1.1 could plumb full per-role
        # importance through the landscape.)
        out.append(SkillTrend(
            canonical_name=c.canonical_name,
            role_count=c.role_count,
            role_share=c.role_count / total,
            role_ids=list(c.role_ids),
            category=c.category,
            importance_max=c.importance_max,
        ))
    out.sort(key=lambda s: (-s.role_count, s.canonical_name.lower()))
    return out


def _category_breakdown(landscape: SkillLandscape) -> CategoryBreakdown:
    counts: Counter[str] = Counter()
    for c in landscape.clusters:
        counts[c.category or "uncategorized"] += 1
    return CategoryBreakdown(counts=dict(counts))


def _domain_breakdown(extractions: dict[str, "ExtractionResult"]) -> DomainBreakdown:
    counts: Counter[str] = Counter()
    for ex in extractions.values():
        counts[ex.role.domain or "general"] += 1
    return DomainBreakdown(counts=dict(counts))


def _seniority_breakdown(extractions: dict[str, "ExtractionResult"]) -> SeniorityBreakdown:
    counts: Counter[str] = Counter()
    for ex in extractions.values():
        sen = getattr(ex.role.seniority, "value", str(ex.role.seniority))
        counts[sen] += 1
    return SeniorityBreakdown(counts=dict(counts))


def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def _bucket_skills(
    role_ids: list[str], extractions: dict[str, "ExtractionResult"]
) -> dict[str, int]:
    """Count how many of the bucket's roles mention each skill (canonical name)."""
    counts: Counter[str] = Counter()
    for rid in role_ids:
        ex = extractions.get(rid)
        if ex is None:
            continue
        seen: set[str] = set()
        for skill in ex.skills:
            name = skill.name.strip()
            if not name or name in seen:
                continue
            seen.add(name)
            counts[name] += 1
    return dict(counts)


def _compute_recency(
    corpus: Corpus,
    extractions: dict[str, "ExtractionResult"],
    *,
    window_days: int,
    today: date | None = None,
) -> RecencySignal | None:
    """Split corpus into recent/prior windows by frontmatter date.

    Returns None when fewer than ``MIN_RECENCY_BUCKET_SIZE`` JDs land on
    each side — recency analysis below that is just noise.
    """
    today = today or datetime.now(timezone.utc).date()
    cutoff = today - timedelta(days=window_days)

    recent_ids: list[str] = []
    prior_ids: list[str] = []
    for entry in corpus:
        d = _parse_date(entry.frontmatter.posted)
        if d is None:
            continue
        (recent_ids if d >= cutoff else prior_ids).append(entry.role_id)

    if (
        len(recent_ids) < MIN_RECENCY_BUCKET_SIZE
        or len(prior_ids) < MIN_RECENCY_BUCKET_SIZE
    ):
        if recent_ids or prior_ids:
            return RecencySignal(
                window_days=window_days,
                note=(
                    f"too few datable JDs to split — "
                    f"recent={len(recent_ids)}, prior={len(prior_ids)} "
                    f"(need ≥{MIN_RECENCY_BUCKET_SIZE} on each side)"
                ),
            )
        return None

    recent = RecencyBucket(
        label="recent",
        role_ids=recent_ids,
        skill_counts=_bucket_skills(recent_ids, extractions),
    )
    prior = RecencyBucket(
        label="prior",
        role_ids=prior_ids,
        skill_counts=_bucket_skills(prior_ids, extractions),
    )

    # Rising / falling — skills with shifting role-share between buckets.
    recent_share = {n: c / len(recent_ids) for n, c in recent.skill_counts.items()}
    prior_share = {n: c / len(prior_ids) for n, c in prior.skill_counts.items()}
    all_skills = set(recent_share) | set(prior_share)
    deltas: list[tuple[str, float]] = []
    for name in all_skills:
        deltas.append((name, recent_share.get(name, 0.0) - prior_share.get(name, 0.0)))
    rising = [n for n, d in sorted(deltas, key=lambda x: -x[1]) if d > 0.15][:10]
    falling = [n for n, d in sorted(deltas, key=lambda x: x[1]) if d < -0.15][:10]

    return RecencySignal(
        window_days=window_days,
        recent=recent,
        prior=prior,
        rising=rising,
        falling=falling,
    )


def compute_trends(
    corpus: Corpus,
    extractions: dict[str, "ExtractionResult"],
    *,
    recency_window_days: int = DEFAULT_RECENCY_WINDOW_DAYS,
    today: date | None = None,
) -> TrendsReport:
    """Build a TrendsReport from a corpus + per-role extractions."""
    landscape = cluster_skills(extractions)
    skills = _to_skill_trends(landscape)
    notes: list[str] = []
    if not skills:
        notes.append("no skills extracted — corpus may be empty or extractions missing")

    recency = _compute_recency(
        corpus, extractions,
        window_days=recency_window_days, today=today,
    )

    return TrendsReport(
        corpus_root=str(corpus.root),
        generated_at=datetime.now(timezone.utc),
        role_count=len(corpus),
        role_ids=[e.role_id for e in corpus],
        skills=skills,
        categories=_category_breakdown(landscape),
        domains=_domain_breakdown(extractions),
        seniority=_seniority_breakdown(extractions),
        recency=recency,
        notes=notes,
    )


def render_trends_markdown(report: TrendsReport, *, top_n: int = 25) -> str:
    """Render a TrendsReport as readable markdown."""
    lines = [
        f"# market trends — {report.corpus_root}",
        "",
        f"_generated: {report.generated_at.isoformat(timespec='seconds')}_  ",
        f"_corpus: {report.role_count} role(s)_",
        "",
    ]

    lines.append("## Top skills by demand")
    lines.append("")
    if not report.skills:
        lines.append("_(no skills)_")
    else:
        lines.append("| Rank | Skill | Roles | Share | Category | Max importance |")
        lines.append("|---:|---|---:|---:|---|---|")
        for i, s in enumerate(report.skills[:top_n], start=1):
            lines.append(
                f"| {i} | {s.canonical_name} | {s.role_count} | "
                f"{s.role_share:.0%} | {s.category or '—'} | "
                f"{s.importance_max or '—'} |"
            )
        if len(report.skills) > top_n:
            lines.append(f"| … | _{len(report.skills) - top_n} more_ |  |  |  |  |")
    lines.append("")

    lines.append("## Category breakdown")
    lines.append("")
    if report.categories.counts:
        for cat, n in sorted(report.categories.counts.items(), key=lambda kv: (-kv[1], kv[0])):
            lines.append(f"- **{cat}**: {n}")
    else:
        lines.append("_(none)_")
    lines.append("")

    lines.append("## Role mix")
    lines.append("")
    if report.domains.counts:
        lines.append("**Domains:** " + ", ".join(
            f"{d}={n}" for d, n in sorted(report.domains.counts.items(), key=lambda kv: (-kv[1], kv[0]))
        ))
    if report.seniority.counts:
        lines.append("**Seniority:** " + ", ".join(
            f"{s}={n}" for s, n in sorted(report.seniority.counts.items(), key=lambda kv: (-kv[1], kv[0]))
        ))
    lines.append("")

    if report.recency is not None:
        lines.append("## Recency signal")
        lines.append("")
        r = report.recency
        if r.note:
            lines.append(f"_{r.note}_")
        else:
            lines.append(
                f"Window: {r.window_days} days · "
                f"recent={len(r.recent.role_ids)} · prior={len(r.prior.role_ids)}"
            )
            if r.rising:
                lines.append("")
                lines.append("**Rising:** " + ", ".join(f"`{n}`" for n in r.rising))
            if r.falling:
                lines.append("")
                lines.append("**Falling:** " + ", ".join(f"`{n}`" for n in r.falling))
            if not r.rising and not r.falling:
                lines.append("")
                lines.append("_no skill saw a >15pt share shift_")
        lines.append("")

    if report.notes:
        lines.append("## Notes")
        lines.append("")
        for n in report.notes:
            lines.append(f"- {n}")
        lines.append("")

    return "\n".join(lines) + "\n"


def write_trends_report(report: TrendsReport, output_dir: Path) -> tuple[Path, Path]:
    """Persist trends.{md,json} under output_dir."""
    output_dir = Path(output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    md_path = output_dir / "market-trends.md"
    md_path.write_text(render_trends_markdown(report), encoding="utf-8")
    json_path = output_dir / "market-trends.json"
    json_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    return md_path, json_path


def trends_for_directory(
    directory: Path,
    *,
    extract: ExtractorFn | None = None,
    client=None,
    use_cache: bool = True,
    recency_window_days: int = DEFAULT_RECENCY_WINDOW_DAYS,
    today: date | None = None,
) -> tuple[Corpus, TrendsReport]:
    """End-to-end: load corpus, extract, compute trends. Mirrors Department's
    ``analyze_directory`` so callers can pass either a stub extractor or
    a live LLM client."""
    directory = validate_dir(directory, entity="jd-folder")
    corpus = load_corpus(directory)
    if extract is None:
        if client is None:
            from agentforge.llm.client import LLMClient
            client = LLMClient()
        from agentforge.department.synthesize import _default_extractor
        extract = _default_extractor(client)
    extractions = extract_corpus(corpus, extract, use_cache=use_cache)
    report = compute_trends(
        corpus, extractions,
        recency_window_days=recency_window_days, today=today,
    )
    return corpus, report
