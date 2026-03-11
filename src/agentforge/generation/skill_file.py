"""Generate SKILL.md files from extraction results."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from agentforge.models.extracted_skills import (
    ExtractionResult,
    SkillCategory,
    SkillProficiency,
    SuggestedTraits,
)
from agentforge.models.job_description import JobDescription


# Trait descriptions keyed by trait name, with thresholds for low/mid/high descriptions
_TRAIT_DESCRIPTORS: dict[str, dict[str, str]] = {
    "warmth": {
        "low": "Reserved and professional",
        "mid": "Approachable and balanced",
        "high": "Highly warm and personable",
        "prompt": "Adjust communication warmth based on context",
    },
    "verbosity": {
        "low": "Concise and to-the-point",
        "mid": "Moderately detailed",
        "high": "Thorough and comprehensive in explanations",
        "prompt": "Calibrate response detail level to audience needs",
    },
    "assertiveness": {
        "low": "Deferential and consensus-seeking",
        "mid": "Balanced confidence",
        "high": "Confident and decisive",
        "prompt": "Take ownership of recommendations and decisions",
    },
    "humor": {
        "low": "Serious and focused",
        "mid": "Occasional light humor",
        "high": "Engages with humor naturally",
        "prompt": "Use humor to build rapport when appropriate",
    },
    "empathy": {
        "low": "Objective and analytical",
        "mid": "Considerate of perspectives",
        "high": "Deeply empathetic and understanding",
        "prompt": "Actively consider emotional context in interactions",
    },
    "directness": {
        "low": "Diplomatic and tactful",
        "mid": "Clear with consideration",
        "high": "Direct and transparent",
        "prompt": "Communicate findings and opinions clearly without hedging",
    },
    "rigor": {
        "low": "Flexible and adaptive",
        "mid": "Methodical with room for creativity",
        "high": "Highly precise and detail-oriented",
        "prompt": "Apply rigorous methodology to analysis and outputs",
    },
    "creativity": {
        "low": "Conventional and proven approaches",
        "mid": "Open to creative solutions",
        "high": "Innovative and experimental",
        "prompt": "Propose novel approaches and think outside established patterns",
    },
    "epistemic_humility": {
        "low": "Confident in knowledge scope",
        "mid": "Acknowledges uncertainty when present",
        "high": "Proactively flags limitations and unknowns",
        "prompt": "Clearly state confidence levels and knowledge boundaries",
    },
    "patience": {
        "low": "Efficient and action-oriented",
        "mid": "Patient with reasonable pacing",
        "high": "Extremely patient and thorough with guidance",
        "prompt": "Allow adequate time for understanding and iteration",
    },
}


def _trait_description(trait_name: str, value: float) -> str:
    """Return a human-readable description for a trait value."""
    desc = _TRAIT_DESCRIPTORS.get(trait_name)
    if not desc:
        return f"Trait value: {value:.0%}"
    if value < 0.35:
        return desc["low"]
    if value < 0.65:
        return desc["mid"]
    return desc["high"]


def _trait_prompt(trait_name: str) -> str:
    """Return a behavior prompt for a trait."""
    desc = _TRAIT_DESCRIPTORS.get(trait_name)
    return desc["prompt"] if desc else ""


def _proficiency_pct(prof: SkillProficiency) -> int:
    """Convert proficiency enum to approximate automation-assist percentage."""
    return {
        SkillProficiency.BEGINNER: 80,
        SkillProficiency.INTERMEDIATE: 60,
        SkillProficiency.ADVANCED: 40,
        SkillProficiency.EXPERT: 20,
    }.get(prof, 50)


class SkillFileGenerator:
    """Generates structured SKILL.md documentation from extraction results.

    Follows best-practice section structure for agent personality and skill
    documentation, designed for interoperability with AI agent frameworks.
    """

    def generate(
        self,
        extraction: ExtractionResult,
        jd: JobDescription | None = None,
    ) -> str:
        """Generate a SKILL.md file from extraction results.

        Args:
            extraction: LLM-extracted role, skills, and trait data.
            jd: Optional parsed job description for additional context
                (company, location, metadata).
        """
        lines: list[str] = []

        # ── YAML Frontmatter (Claude Code compatible) ──
        self._render_frontmatter(lines, extraction)

        # ── Header ──
        self._render_header(lines, extraction, jd)

        # ── Role Context ──
        self._render_role_context(lines, extraction, jd)

        # ── Skills by category ──
        self._render_skills(lines, extraction)

        # ── Personality Profile ──
        self._render_personality_profile(lines, extraction.suggested_traits)

        # ── Scope ──
        self._render_scope(lines, extraction)

        # ── Key Responsibilities ──
        self._render_responsibilities(lines, extraction)

        # ── Qualifications ──
        self._render_qualifications(lines, extraction)

        # ── Automation Assessment ──
        self._render_automation(lines, extraction)

        # ── Embedded Data ──
        self._render_embedded_data(lines, extraction)

        # ── Metadata Footer ──
        self._render_metadata_footer(lines, extraction, jd)

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Section renderers
    # ------------------------------------------------------------------

    def _render_frontmatter(
        self,
        lines: list[str],
        extraction: ExtractionResult,
    ) -> None:
        """Render YAML frontmatter for Claude Code compatibility."""
        from agentforge.utils import safe_filename
        import re

        skill_name = safe_filename(extraction.role.title).lower().replace("_", "-")
        skill_name = re.sub(r"-+", "-", skill_name).strip("-") or "generated-skill"

        description = extraction.role.purpose
        if len(description) > 200:
            description = description[:197] + "..."

        lines.append("---")
        lines.append(f"name: {skill_name}")
        lines.append(f"description: {description}")
        lines.append("allowed-tools: Read, Grep, Glob, Bash, Write, Edit")
        lines.append("---")
        lines.append("")

    def _render_header(
        self,
        lines: list[str],
        extraction: ExtractionResult,
        jd: JobDescription | None,
    ) -> None:
        """Render title, purpose statement, and key metadata."""
        lines.append(f"# {extraction.role.title}")
        lines.append("")
        lines.append(f"> {extraction.role.purpose}")
        lines.append("")

        lines.append(f"**Domain:** {extraction.role.domain}")
        lines.append(f"**Seniority:** {extraction.role.seniority.value}")
        pct = int(extraction.automation_potential * 100)
        rationale_short = ""
        if extraction.automation_rationale:
            # Use first sentence of rationale for the header line
            first_sentence = extraction.automation_rationale.split(".")[0].strip()
            if first_sentence:
                rationale_short = f" ({first_sentence})"
        lines.append(f"**Automation Potential:** {pct}%{rationale_short}")
        lines.append("")

    def _render_role_context(
        self,
        lines: list[str],
        extraction: ExtractionResult,
        jd: JobDescription | None,
    ) -> None:
        """Render real-world role context: location, company, audience."""
        context_items: list[tuple[str, str]] = []

        if jd:
            if jd.location:
                context_items.append(("Location", jd.location))
            if jd.company:
                context_items.append(("Company/Organization", jd.company))
            if jd.department:
                context_items.append(("Department", jd.department))

        context_items.append(("Industry/Domain", extraction.role.domain))

        if extraction.role.audience:
            context_items.append(("Target Audience", ", ".join(extraction.role.audience)))

        if context_items:
            lines.append("## Role Context")
            lines.append("")
            for label, value in context_items:
                lines.append(f"- **{label}:** {value}")
            lines.append("")

    def _render_skills(self, lines: list[str], extraction: ExtractionResult) -> None:
        """Render skills grouped by category with proficiency, importance, examples, and GenAI notes."""
        categories = {
            SkillCategory.HARD: "Technical Skills",
            SkillCategory.SOFT: "Soft Skills",
            SkillCategory.DOMAIN: "Domain Knowledge",
            SkillCategory.TOOL: "Tools & Platforms",
        }

        for cat, heading in categories.items():
            cat_skills = [s for s in extraction.skills if s.category == cat]
            if cat_skills:
                lines.append(f"## {heading}")
                lines.append("")
                for skill in cat_skills:
                    importance_badge = {
                        "required": "[Required]",
                        "preferred": "[Preferred]",
                        "nice_to_have": "[Nice to Have]",
                    }.get(skill.importance.value, "")
                    lines.append(
                        f"- **{skill.name}** ({skill.proficiency.value}) "
                        f"{importance_badge}"
                    )
                    if skill.context:
                        lines.append(f"  - {skill.context}")
                    # Render specific tool/library examples
                    if skill.examples:
                        examples_str = "; ".join(skill.examples)
                        lines.append(f"  - *Examples:* {examples_str}")
                    # Render GenAI/ML application notes
                    if skill.genai_application:
                        lines.append(f"  - *GenAI Application:* {skill.genai_application}")
                lines.append("")

    def _render_personality_profile(
        self,
        lines: list[str],
        traits: SuggestedTraits,
    ) -> None:
        """Render personality traits with descriptions, prompts, and customization guidance."""
        defined = traits.defined_traits()
        if not defined:
            return

        lines.append("## Personality Profile")
        lines.append("")

        # Sort traits by value descending so strongest traits appear first
        sorted_traits = sorted(defined.items(), key=lambda x: x[1], reverse=True)

        for trait_name, value in sorted_traits:
            display_name = trait_name.replace("_", " ").title()
            desc = _trait_description(trait_name, value)
            prompt = _trait_prompt(trait_name)
            lines.append(
                f"- **{display_name}** ({value:.0%}): {desc}"
            )
            if prompt:
                lines.append(f"  - *Behavior prompt:* {prompt}")
        lines.append("")

        # Customization guidance for open-source modularity
        lines.append("> **Customization Note:** Trait values are starting points derived from "
                      "the job description. Scale traits up or down to create personality variants "
                      "(e.g., boost Creativity to 90% for an innovative agent, or lower Directness "
                      "to 30% for a more diplomatic one). Mix traits from multiple SKILL.md profiles "
                      "to create hybrid personas. Community contributions of trait presets are welcome.")
        lines.append("")

    def _render_scope(self, lines: list[str], extraction: ExtractionResult) -> None:
        """Render primary and secondary scope."""
        if extraction.role.scope_primary:
            lines.append("## Primary Scope")
            lines.append("")
            for item in extraction.role.scope_primary:
                lines.append(f"- {item}")
            lines.append("")

        if extraction.role.scope_secondary:
            lines.append("## Secondary Scope")
            lines.append("")
            for item in extraction.role.scope_secondary:
                lines.append(f"- {item}")
            lines.append("")

    def _render_responsibilities(
        self, lines: list[str], extraction: ExtractionResult
    ) -> None:
        """Render key responsibilities."""
        if not extraction.responsibilities:
            return
        lines.append("## Key Responsibilities")
        lines.append("")
        for i, resp in enumerate(extraction.responsibilities, 1):
            lines.append(f"{i}. {resp}")
        lines.append("")

    def _render_qualifications(
        self, lines: list[str], extraction: ExtractionResult
    ) -> None:
        """Render qualifications."""
        if not extraction.qualifications:
            return
        lines.append("## Qualifications")
        lines.append("")
        for qual in extraction.qualifications:
            lines.append(f"- {qual}")
        lines.append("")

    def _render_automation(
        self, lines: list[str], extraction: ExtractionResult
    ) -> None:
        """Render automation assessment with structured breakdown and per-area estimates."""
        pct = int(extraction.automation_potential * 100)

        lines.append("## Automation Assessment")
        lines.append("")
        lines.append(f"**Overall Automation Potential:** {pct}%")
        lines.append("")

        if extraction.automation_rationale:
            lines.append(extraction.automation_rationale)
            lines.append("")

        # ── AI-Augmentable areas (tools + hard skills with high proficiency) ──
        ai_areas: list[str] = []
        human_areas: list[str] = []

        for skill in extraction.skills:
            if skill.category == SkillCategory.TOOL:
                est_pct = _proficiency_pct(skill.proficiency)
                label = f"{skill.name} ({est_pct}%)"
                detail = skill.context or ""
                if skill.genai_application:
                    detail = skill.genai_application
                if detail:
                    label += f" — {detail}"
                ai_areas.append(label)
            elif skill.category == SkillCategory.HARD and skill.genai_application:
                est_pct = _proficiency_pct(skill.proficiency)
                ai_areas.append(
                    f"{skill.name} ({est_pct}%) — {skill.genai_application}"
                )
            elif skill.category == SkillCategory.SOFT:
                detail = skill.context or ""
                entry = f"{skill.name}"
                if detail:
                    entry += f" — {detail}"
                human_areas.append(entry)

        if ai_areas:
            lines.append("**AI-Augmentable Areas:**")
            for item in ai_areas:
                lines.append(f"- {item}")
            lines.append("")

        if human_areas:
            lines.append("**Human-Critical Areas:**")
            for item in human_areas:
                lines.append(f"- {item}")
            lines.append("")

    def _render_embedded_data(
        self, lines: list[str], extraction: ExtractionResult
    ) -> None:
        """Render a comprehensive embedded JSON for programmatic consumption."""
        # Full skills array grouped by category
        skills_by_cat: dict[str, list[dict[str, Any]]] = {}
        for skill in extraction.skills:
            cat_key = skill.category.value
            entry: dict[str, Any] = {
                "name": skill.name,
                "proficiency": skill.proficiency.value,
                "importance": skill.importance.value,
            }
            if skill.context:
                entry["context"] = skill.context
            if skill.examples:
                entry["examples"] = skill.examples
            if skill.genai_application:
                entry["genai_application"] = skill.genai_application
            skills_by_cat.setdefault(cat_key, []).append(entry)

        # Domain knowledge as a dedicated array
        domain_knowledge = skills_by_cat.get("domain", [])

        summary: dict[str, Any] = {
            "role": extraction.role.title,
            "domain": extraction.role.domain,
            "seniority": extraction.role.seniority.value,
            "automation_potential": extraction.automation_potential,
            "skills": skills_by_cat,
            "domain_knowledge": domain_knowledge,
            "responsibilities": extraction.responsibilities,
            "qualifications": extraction.qualifications,
        }

        # Include trait summary
        defined_traits = extraction.suggested_traits.defined_traits()
        if defined_traits:
            summary["personality"] = {k: round(v, 2) for k, v in defined_traits.items()}

        # Scope
        if extraction.role.scope_primary:
            summary["scope"] = {
                "primary": extraction.role.scope_primary,
            }
            if extraction.role.scope_secondary:
                summary["scope"]["secondary"] = extraction.role.scope_secondary

        if extraction.role.audience:
            summary["audience"] = extraction.role.audience

        lines.append("## Agent Data (Machine-Readable)")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(summary, indent=2))
        lines.append("```")
        lines.append("")

    def _render_metadata_footer(
        self,
        lines: list[str],
        extraction: ExtractionResult,
        jd: JobDescription | None,
    ) -> None:
        """Render metadata footer with version, source, and timestamp."""
        lines.append("---")
        lines.append("")

        source_info = "Unknown"
        if jd:
            source_info = jd.title
            if jd.company:
                source_info += f" at {jd.company}"

        lines.append(f"*Generated by AgentForge* | "
                      f"Source: {source_info} | "
                      f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}*")
        lines.append("")
