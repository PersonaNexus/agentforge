"""Department Phase 1.1 — team synthesis.

Phase 1.0 (``synthesize.analyze_directory``) produced a *report*. This
module produces the actual department: per-role identity + skill
folders, a ``_shared/`` skill library for clusters that span ≥2 roles,
a conductor agent, an ``orchestration.yaml`` handoff graph, and a
README.

Designed so the LLM-bearing pieces (handoff judge, team-brief writer)
are optional: with ``client=None`` everything still runs and the LLM
surfaces degrade to deterministic fallbacks.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from pydantic import BaseModel, Field

from agentforge.corpus import Corpus, JDEntry
from agentforge.department.cluster import SkillCluster, SkillLandscape, cluster_skills
from agentforge.department.conductor import (
    build_conductor_identity,
    render_conductor_skill_md,
    render_conductor_yaml,
)
from agentforge.department.handoffs import HandoffGraph, detect_handoffs, render_orchestration_yaml
from agentforge.department.readme import render_readme
from agentforge.department.synthesize import extract_corpus
from agentforge.generation.identity_generator import IdentityGenerator
from agentforge.generation.skill_folder import SkillFolderGenerator
from agentforge.models.extracted_skills import ExtractionResult
from agentforge.models.job_description import JobDescription
from agentforge.utils import make_skill_slug, safe_rel_path

if TYPE_CHECKING:
    from agentforge.llm.client import LLMClient


# Targets that suppress identity.yaml writes (mirrors forge --target).
_YAML_TARGETS_SKIPPING = {"openclaw", "plain"}


class RoleArtifact(BaseModel):
    """Files produced for one role under <output>/<role-id>/."""

    role_id: str
    identity_yaml_path: str | None = None
    skill_md_path: str
    supplementary_paths: list[str] = Field(default_factory=list)


class TeamArtifacts(BaseModel):
    """All paths produced by a synthesize run."""

    department_name: str
    output_dir: str
    readme_path: str
    orchestration_path: str
    conductor_identity_path: str | None
    conductor_skill_path: str
    role_artifacts: list[RoleArtifact] = Field(default_factory=list)
    shared_skill_paths: list[str] = Field(default_factory=list)
    handoff_count: int = 0
    shared_cluster_count: int = 0
    generated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )


def _entry_to_jd(entry: JDEntry) -> JobDescription:
    """Build a forge JobDescription from a corpus entry."""
    return JobDescription(
        title=entry.frontmatter.title,
        raw_text=entry.body,
    )


def _shared_skill_md(cluster: SkillCluster) -> str:
    """Render a small markdown stub for a shared skill cluster."""
    members = ", ".join(f"`{n}`" for n in sorted(set(cluster.member_names))) or "—"
    roles = ", ".join(f"`{r}`" for r in cluster.role_ids) or "—"
    return (
        f"# {cluster.canonical_name}\n\n"
        f"**Category:** {cluster.category or '—'}  \n"
        f"**Importance (max across roles):** {cluster.importance_max or '—'}  \n"
        f"**Used by:** {roles}\n\n"
        f"**Phrasings observed:** {members}\n\n"
        "## Why this is shared\n\n"
        "This capability appears in 2+ role JDs in this department. Treat the "
        "guidance below as the team-level expectation; per-role skill folders "
        "may extend it.\n"
    )


def _write_shared_library(
    landscape: SkillLandscape,
    output_dir: Path,
) -> tuple[list[Path], dict[str, str]]:
    """Write `_shared/skills/<slug>.md` for each shared cluster.

    Returns (paths, slug_index) where slug_index maps canonical_name → slug
    so per-role outputs can cross-link.
    """
    shared_dir = output_dir / "_shared" / "skills"
    shared_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    slug_index: dict[str, str] = {}
    used_slugs: set[str] = set()
    for cluster in landscape.shared_clusters:
        slug = make_skill_slug(cluster.canonical_name) or "shared-skill"
        # Disambiguate collisions deterministically.
        candidate = slug
        n = 2
        while candidate in used_slugs:
            candidate = f"{slug}-{n}"
            n += 1
        slug = candidate
        used_slugs.add(slug)
        slug_index[cluster.canonical_name] = slug
        path = shared_dir / f"{slug}.md"
        path.write_text(_shared_skill_md(cluster), encoding="utf-8")
        paths.append(path)
    return paths, slug_index


def _shared_reference_section(
    role_id: str,
    landscape: SkillLandscape,
    slug_index: dict[str, str],
) -> str:
    """Build the 'shared with the team' section appended to per-role SKILL.md."""
    used = [c for c in landscape.shared_clusters if role_id in c.role_ids]
    if not used:
        return ""
    lines = ["", "## Shared with the team", "",
             "Capabilities below are shared across the department. The "
             "team-level guidance lives in `_shared/skills/` — extend it "
             "here when this role applies it differently.", ""]
    for c in used:
        slug = slug_index.get(c.canonical_name)
        if not slug:
            continue
        lines.append(
            f"- **{c.canonical_name}** → `../_shared/skills/{slug}.md` "
            f"(also used by: "
            + ", ".join(f"`{r}`" for r in c.role_ids if r != role_id)
            + ")"
        )
    lines.append("")
    return "\n".join(lines)


def _write_role(
    entry: JDEntry,
    extraction: ExtractionResult,
    output_dir: Path,
    *,
    target: str,
    keep_identity_yaml: bool,
    landscape: SkillLandscape,
    slug_index: dict[str, str],
) -> RoleArtifact:
    """Per-role identity + skill folder write."""
    role_dir = output_dir / entry.role_id
    role_dir.mkdir(parents=True, exist_ok=True)

    jd = _entry_to_jd(entry)
    identity_gen = IdentityGenerator()
    identity, identity_yaml = identity_gen.generate(extraction)
    skill_gen = SkillFolderGenerator()
    skill_folder = skill_gen.generate(extraction, identity, jd=jd)

    artifact = RoleArtifact(
        role_id=entry.role_id,
        skill_md_path=str(role_dir / "SKILL.md"),
    )

    write_identity = keep_identity_yaml or target not in _YAML_TARGETS_SKIPPING
    if write_identity:
        identity_path = role_dir / "identity.yaml"
        identity_path.write_text(identity_yaml, encoding="utf-8")
        artifact.identity_yaml_path = str(identity_path)

    skill_md = skill_folder.skill_md_with_references()
    skill_md += _shared_reference_section(entry.role_id, landscape, slug_index)
    (role_dir / "SKILL.md").write_text(skill_md, encoding="utf-8")

    for rel_path, content in skill_folder.supplementary_files.items():
        target_path = safe_rel_path(role_dir, rel_path)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(content, encoding="utf-8")
        artifact.supplementary_paths.append(str(target_path))

    return artifact


def synthesize_team(
    corpus: Corpus,
    output_dir: Path,
    *,
    department_name: str | None = None,
    extract: Callable[[JDEntry], ExtractionResult] | None = None,
    extractions: dict[str, ExtractionResult] | None = None,
    client: "LLMClient | None" = None,
    use_llm_handoffs: bool = False,
    use_llm_brief: bool = False,
    target: str = "claude-code",
    keep_identity_yaml: bool = False,
    use_cache: bool = True,
) -> TeamArtifacts:
    """End-to-end Phase 1.1 synthesis.

    Args:
        corpus: Loaded JD corpus.
        output_dir: Directory to write the synthesized team into.
        department_name: Display name; defaults to the corpus directory name.
        extract: Per-JD extractor. Required if ``extractions`` not supplied.
        extractions: Pre-computed extractions to reuse (bypasses ``extract``).
        client: LLM client used by handoff judge / brief writer when enabled.
        use_llm_handoffs: When True and ``client`` is set, infer handoffs.
        use_llm_brief: When True and ``client`` is set, write README team brief.
        target: ``"claude-code"`` (default) writes identity.yaml; ``"plain"`` /
            ``"openclaw"`` suppresses it (mirrors forge --target semantics).
        keep_identity_yaml: Override the suppression for plain/openclaw.
        use_cache: Pass-through to ``extract_corpus`` cache.
    """
    output_dir = Path(output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if department_name is None:
        department_name = Path(corpus.root).name or "department"

    if extractions is None:
        if extract is None:
            raise ValueError("synthesize_team requires either extractions= or extract=")
        extractions = extract_corpus(corpus, extract, use_cache=use_cache)

    landscape = cluster_skills(extractions)

    shared_paths, slug_index = _write_shared_library(landscape, output_dir)

    role_artifacts: list[RoleArtifact] = []
    for entry in corpus:
        ex = extractions.get(entry.role_id)
        if ex is None:
            continue
        role_artifacts.append(_write_role(
            entry, ex, output_dir,
            target=target,
            keep_identity_yaml=keep_identity_yaml,
            landscape=landscape,
            slug_index=slug_index,
        ))

    handoff_client = client if use_llm_handoffs else None
    graph = detect_handoffs(corpus, extractions, client=handoff_client)
    orchestration_path = output_dir / "orchestration.yaml"
    orchestration_path.write_text(render_orchestration_yaml(graph), encoding="utf-8")

    conductor_dir = output_dir / "_conductor"
    conductor_dir.mkdir(parents=True, exist_ok=True)
    conductor_identity_path: Path | None = None
    if keep_identity_yaml or target not in _YAML_TARGETS_SKIPPING:
        conductor_identity_path = conductor_dir / "identity.yaml"
        identity = build_conductor_identity(corpus, extractions, graph, department_name)
        conductor_identity_path.write_text(render_conductor_yaml(identity), encoding="utf-8")
    conductor_skill_path = conductor_dir / "SKILL.md"
    conductor_skill_path.write_text(
        render_conductor_skill_md(department_name, corpus, extractions, graph),
        encoding="utf-8",
    )

    brief_client = client if use_llm_brief else None
    readme_path = output_dir / "README.md"
    readme_path.write_text(
        render_readme(department_name, corpus, extractions, landscape, graph, client=brief_client),
        encoding="utf-8",
    )

    return TeamArtifacts(
        department_name=department_name,
        output_dir=str(output_dir),
        readme_path=str(readme_path),
        orchestration_path=str(orchestration_path),
        conductor_identity_path=str(conductor_identity_path) if conductor_identity_path else None,
        conductor_skill_path=str(conductor_skill_path),
        role_artifacts=role_artifacts,
        shared_skill_paths=[str(p) for p in shared_paths],
        handoff_count=len(graph.handoffs),
        shared_cluster_count=len(landscape.shared_clusters),
    )
