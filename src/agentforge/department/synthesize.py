"""Top-level orchestration for the ``department`` command (Phase 1.0).

Phase 1.0 = analysis only: load corpus, extract per role, cluster skills,
render report. Phase 1.1 will add the synthesis side (per-role identity
generation, shared resources, conductor, orchestration.yaml).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from agentforge.corpus import Corpus, JDEntry, load_corpus
from agentforge.corpus import cache as corpus_cache
from agentforge.department.cluster import SkillLandscape, cluster_skills
from agentforge.models.extracted_skills import ExtractionResult
from agentforge.models.job_description import JobDescription


# Caller-supplied extractor signature: (JDEntry) -> ExtractionResult.
# Defined as a callable so tests can pass a stub without touching the LLM.
ExtractorFn = Callable[[JDEntry], ExtractionResult]


def _default_extractor(client) -> ExtractorFn:
    """Build an extractor that wraps the existing SkillExtractor."""
    from agentforge.extraction.skill_extractor import SkillExtractor
    extractor = SkillExtractor(client=client)

    def _extract(entry: JDEntry) -> ExtractionResult:
        jd = JobDescription(
            title=entry.title,
            raw_text=entry.body,
        )
        return extractor.extract(jd)

    return _extract


def extract_corpus(
    corpus: Corpus,
    extract: ExtractorFn,
    *,
    use_cache: bool = True,
) -> dict[str, ExtractionResult]:
    """Run extraction across every JD in the corpus, caching by body hash."""
    corpus_root = Path(corpus.root)
    out: dict[str, ExtractionResult] = {}
    for entry in corpus:
        cached = corpus_cache.load(corpus_root, entry) if use_cache else None
        if cached is not None:
            out[entry.role_id] = ExtractionResult.model_validate(cached)
            continue
        result = extract(entry)
        out[entry.role_id] = result
        if use_cache:
            corpus_cache.save(corpus_root, entry, result.model_dump(mode="json"))
    return out


def analyze_directory(
    directory: Path,
    extract: ExtractorFn | None = None,
    client=None,
    *,
    use_cache: bool = True,
) -> tuple[Corpus, dict[str, ExtractionResult], SkillLandscape]:
    """End-to-end Phase-1.0 analysis: load → extract → cluster."""
    corpus = load_corpus(directory)
    if extract is None:
        if client is None:
            from agentforge.llm.client import LLMClient
            client = LLMClient()
        extract = _default_extractor(client)
    extractions = extract_corpus(corpus, extract, use_cache=use_cache)
    landscape = cluster_skills(extractions)
    return corpus, extractions, landscape


def render_report_markdown(
    corpus: Corpus,
    extractions: dict[str, ExtractionResult],
    landscape: SkillLandscape,
) -> str:
    """Render a human-readable skill-landscape report."""
    lines: list[str] = [
        f"# department — skill landscape",
        "",
        f"- Corpus: `{corpus.root}`",
        f"- Roles ({landscape.role_count}): "
        + ", ".join(f"`{r}`" for r in landscape.role_ids),
        f"- Generated: {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        "",
        "## Per-role summary",
        "",
        "| Role | Title | Skills extracted |",
        "|---|---|---:|",
    ]
    for entry in corpus:
        result = extractions.get(entry.role_id)
        n = len(result.skills) if result else 0
        lines.append(f"| `{entry.role_id}` | {entry.title} | {n} |")
    lines.append("")

    shared = landscape.shared_clusters
    role_specific = landscape.role_specific_clusters

    lines.extend([
        "## Shared skills (appear in 2+ roles)",
        "",
        f"_{len(shared)} clusters._ Candidates to factor into a "
        "department-level shared skill library.",
        "",
    ])
    if shared:
        lines.extend([
            "| Skill | Roles | Category | Max importance |",
            "|---|---:|---|---|",
        ])
        for c in shared:
            roles_str = ", ".join(f"`{r}`" for r in c.role_ids)
            lines.append(
                f"| {c.canonical_name} | {c.role_count} | "
                f"{c.category or '—'} | {c.importance_max or '—'} | "
                f"<br/>roles: {roles_str}"
            )
        lines.append("")
    else:
        lines.append("_(none — no overlap detected)_\n")

    lines.extend([
        "## Role-specific skills",
        "",
        f"_{len(role_specific)} clusters._ Skills unique to one role.",
        "",
    ])
    by_role: dict[str, list] = {r: [] for r in landscape.role_ids}
    for c in role_specific:
        if c.role_ids:
            by_role.setdefault(c.role_ids[0], []).append(c)
    for role_id in landscape.role_ids:
        items = by_role.get(role_id, [])
        if not items:
            continue
        lines.append(f"### `{role_id}` ({len(items)})")
        lines.append("")
        for c in items[:30]:
            lines.append(f"- **{c.canonical_name}** ({c.category or '—'}, "
                        f"{c.importance_max or '—'})")
        if len(items) > 30:
            lines.append(f"- _… {len(items) - 30} more_")
        lines.append("")

    return "\n".join(lines) + "\n"


def write_report(
    corpus: Corpus,
    extractions: dict[str, ExtractionResult],
    landscape: SkillLandscape,
    output_dir: Path,
) -> tuple[Path, Path]:
    """Persist report.md + landscape.json under output_dir."""
    output_dir = Path(output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    md = render_report_markdown(corpus, extractions, landscape)
    md_path = output_dir / "skill-landscape.md"
    md_path.write_text(md, encoding="utf-8")
    json_path = output_dir / "skill-landscape.json"
    json_path.write_text(landscape.model_dump_json(indent=2), encoding="utf-8")
    return md_path, json_path
