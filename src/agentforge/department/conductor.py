"""Conductor agent generation for synthesized departments.

The conductor is a routing-focused agent that knows the department's
roster + the inferred handoff graph and dispatches incoming requests
to the right specialist. We synthesize it deterministically rather
than via the full forge pipeline because all of its inputs are already
known: role IDs, role purposes, and the orchestration edges.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from agentforge.corpus import Corpus
    from agentforge.department.handoffs import HandoffGraph
    from agentforge.models.extracted_skills import ExtractionResult


def _role_brief(entry, extraction: "ExtractionResult | None") -> dict:
    """One-line entry per role used in the conductor's routing table."""
    purpose = (extraction.role.purpose if extraction else "") or ""
    return {
        "role_id": entry.role_id,
        "title": entry.frontmatter.title,
        "purpose": purpose.strip(),
    }


def build_conductor_identity(
    corpus: "Corpus",
    extractions: dict[str, "ExtractionResult"],
    graph: "HandoffGraph",
    department_name: str,
) -> dict:
    """Build a conductor identity dict (PersonaNexus-shaped)."""
    routing_table = [_role_brief(e, extractions.get(e.role_id)) for e in corpus]
    handoff_summary = [
        {"from": h.from_role, "to": h.to_role, "artifact": h.artifact}
        for h in graph.handoffs
    ]

    role_id = f"{department_name}-conductor"
    return {
        "schema_version": "1.0",
        "metadata": {
            "id": role_id,
            "name": f"{department_name.title()} Conductor",
            "description": (
                f"Routes incoming requests for the {department_name} team to "
                f"the right specialist and manages handoffs between roles."
            ),
        },
        "role": {
            "title": f"{department_name.title()} Conductor",
            "purpose": (
                "Triage incoming work, identify which specialist owns it, and "
                "manage cross-role handoffs so nothing drops between roles."
            ),
            "domain": "team-orchestration",
            "seniority": "lead",
        },
        "personality": {
            "traits": {
                "directness": 0.8,
                "rigor": 0.8,
                "warmth": 0.5,
                "epistemic_humility": 0.7,
            },
        },
        "communication": {
            "style": "concise, decision-first, names the owner",
        },
        "expertise": {
            "specialty": f"orchestrating the {department_name} team",
            "routing_table": routing_table,
            "handoffs": handoff_summary,
        },
        "principles": [
            "Always name the owner before discussing the work.",
            "Surface a handoff explicitly — never silently re-route work.",
            "If two specialists could own a request, ask the user; don't guess.",
        ],
        "guardrails": {
            "do_not": [
                "Take on specialist work yourself.",
                "Hide handoffs from the requester.",
            ],
        },
    }


def render_conductor_yaml(identity: dict) -> str:
    """Serialize identity dict to clean YAML (mirrors IdentityGenerator)."""
    clean = json.loads(json.dumps(identity, default=str))
    return yaml.dump(clean, default_flow_style=False, sort_keys=False, allow_unicode=True)


def render_conductor_skill_md(
    department_name: str,
    corpus: "Corpus",
    extractions: dict[str, "ExtractionResult"],
    graph: "HandoffGraph",
) -> str:
    """A minimal SKILL.md for the conductor — routing rules + handoff table."""
    lines = [
        f"# {department_name.title()} Conductor",
        "",
        "## Role",
        "",
        f"Route work into the {department_name} team. Don't do specialist work; "
        "name the owner and the handoff path.",
        "",
        "## Roster",
        "",
        "| role_id | title | purpose |",
        "|---|---|---|",
    ]
    for entry in corpus:
        ex = extractions.get(entry.role_id)
        purpose = (ex.role.purpose if ex else "") or "—"
        lines.append(f"| `{entry.role_id}` | {entry.frontmatter.title} | {purpose} |")
    lines.append("")
    lines.append("## Handoffs")
    lines.append("")
    if not graph.handoffs:
        lines.append("_No handoffs inferred — run `department synthesize --use-llm` to populate._")
    else:
        lines.append("| from | to | trigger | artifact |")
        lines.append("|---|---|---|---|")
        for h in graph.handoffs:
            lines.append(
                f"| `{h.from_role}` | `{h.to_role}` | "
                f"{h.trigger or '—'} | {h.artifact or '—'} |"
            )
    lines.append("")
    lines.append("## Routing rules")
    lines.append("")
    lines.append(
        "1. Read the request. Identify the primary artifact involved.\n"
        "2. Match it against the **artifact** column above to find the producer or owner.\n"
        "3. If multiple roles could own it, ask the user to disambiguate.\n"
        "4. Name the owner explicitly: \"This is `<role_id>`'s — handing off.\"\n"
        "5. After handoff, track until the artifact comes back or escalates."
    )
    lines.append("")
    return "\n".join(lines) + "\n"
