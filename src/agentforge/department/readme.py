"""Department README generation.

Two modes:
  - deterministic (default): templated overview built from corpus + landscape
  - LLM-augmented (``client`` provided): adds a written team brief on top
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agentforge.corpus import Corpus
    from agentforge.department.cluster import SkillLandscape
    from agentforge.department.handoffs import HandoffGraph
    from agentforge.llm.client import LLMClient
    from agentforge.models.extracted_skills import ExtractionResult


def _deterministic_readme(
    department_name: str,
    corpus: "Corpus",
    extractions: dict[str, "ExtractionResult"],
    landscape: "SkillLandscape",
    graph: "HandoffGraph",
) -> str:
    lines = [
        f"# {department_name.title()} Department",
        "",
        f"Synthesized by `agentforge department synthesize` from "
        f"`{corpus.root}` ({landscape.role_count} role(s)).",
        "",
        "## Roster",
        "",
        "| Role | Title | Purpose |",
        "|---|---|---|",
    ]
    for entry in corpus:
        ex = extractions.get(entry.role_id)
        purpose = ((ex.role.purpose if ex else "") or "—").replace("\n", " ").strip()
        if len(purpose) > 120:
            purpose = purpose[:117] + "..."
        lines.append(f"| `{entry.role_id}` | {entry.frontmatter.title} | {purpose} |")
    lines.append("")

    shared = landscape.shared_clusters
    lines.extend([
        "## Shared capabilities",
        "",
        f"_{len(shared)} skill cluster(s) appear in 2+ roles_ — see `_shared/skills/`.",
        "",
    ])
    for c in shared[:15]:
        lines.append(
            f"- **{c.canonical_name}** — used by "
            + ", ".join(f"`{r}`" for r in c.role_ids)
        )
    if len(shared) > 15:
        lines.append(f"- _… {len(shared) - 15} more in `_shared/skills/`_")
    lines.append("")

    lines.extend([
        "## Handoffs",
        "",
        f"_{len(graph.handoffs)} edge(s) — full graph in `orchestration.yaml`._",
        "",
    ])
    if graph.handoffs:
        lines.append("| from | to | artifact |")
        lines.append("|---|---|---|")
        for h in graph.handoffs:
            lines.append(
                f"| `{h.from_role}` | `{h.to_role}` | {h.artifact or '—'} |"
            )
    else:
        lines.append("_No handoffs inferred. Run with `--use-llm` to populate._")
    lines.append("")

    lines.extend([
        "## Layout",
        "",
        "```",
        "<output>/",
        "├── README.md             ← this file",
        "├── orchestration.yaml    ← handoff graph",
        "├── _shared/",
        "│   └── skills/           ← skills that appear in 2+ roles",
        "├── _conductor/",
        "│   ├── identity.yaml",
        "│   └── SKILL.md",
        "└── <role-id>/",
        "    ├── identity.yaml",
        "    └── SKILL.md (+ instructions/, templates/, etc.)",
        "```",
        "",
    ])
    return "\n".join(lines) + "\n"


_BRIEF_SYSTEM = (
    "You are writing a one-paragraph team brief for a synthesized department. "
    "Tone: confident, direct, factual. No marketing language. 4-6 sentences."
)


def _llm_team_brief(
    department_name: str,
    corpus: "Corpus",
    extractions: dict[str, "ExtractionResult"],
    graph: "HandoffGraph",
    client: "LLMClient",
) -> str:
    role_lines = []
    for entry in corpus:
        ex = extractions.get(entry.role_id)
        purpose = (ex.role.purpose if ex else "") or ""
        role_lines.append(f"- {entry.role_id}: {entry.frontmatter.title} — {purpose}")
    handoff_lines = [
        f"- {h.from_role} → {h.to_role}: {h.artifact}" for h in graph.handoffs
    ] or ["(none)"]

    prompt = (
        f"Department name: {department_name}\n\n"
        "Roles:\n" + "\n".join(role_lines) + "\n\n"
        "Handoffs:\n" + "\n".join(handoff_lines) + "\n\n"
        "Write the team brief."
    )
    return client.generate(prompt=prompt, system=_BRIEF_SYSTEM, max_tokens=600).strip()


def render_readme(
    department_name: str,
    corpus: "Corpus",
    extractions: dict[str, "ExtractionResult"],
    landscape: "SkillLandscape",
    graph: "HandoffGraph",
    client: "LLMClient | None" = None,
) -> str:
    """Render the department README. ``client`` enables an LLM team brief."""
    base = _deterministic_readme(department_name, corpus, extractions, landscape, graph)
    if client is None:
        return base
    try:
        brief = _llm_team_brief(department_name, corpus, extractions, graph, client)
    except Exception:
        # Don't fail the whole synthesize on a brief-writer hiccup.
        return base
    if not brief:
        return base
    # Insert the brief right after the title.
    lines = base.split("\n")
    title_idx = 0
    out: list[str] = []
    for i, line in enumerate(lines):
        out.append(line)
        if i == title_idx:
            out.append("")
            out.append("## Team brief")
            out.append("")
            out.append(brief)
    return "\n".join(out)
