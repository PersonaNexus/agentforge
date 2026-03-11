"""Generate Claude Code-compatible skill folders from extraction results.

Produces a skill folder containing a single SKILL.md file with YAML
frontmatter (name, description, allowed-tools) followed by markdown
instructions — the exact format Claude Code expects for drag-and-drop
skill installation.

Claude Code skill spec:
    <skill-name>/
    └── SKILL.md   ← YAML frontmatter + markdown body
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from agentforge.models.extracted_skills import (
    ExtractionResult,
    SkillCategory,
)
from agentforge.models.job_description import JobDescription
from agentforge.generation.skill_file import (
    _trait_description,
    _trait_prompt,
)
from agentforge.utils import safe_filename


class SkillFolderResult(BaseModel):
    """Container for Claude Code-compatible skill folder content."""

    skill_name: str = Field(..., description="Slug name for the skill folder")
    skill_md: str = Field(..., description="SKILL.md content with YAML frontmatter")


class SkillFolderGenerator:
    """Generates Claude Code-compatible skill folders from extraction results.

    Produces a single SKILL.md with YAML frontmatter metadata and markdown
    instructions, matching the Claude Code skill specification.
    """

    def generate(
        self,
        extraction: ExtractionResult,
        identity: Any,
        jd: JobDescription | None = None,
    ) -> SkillFolderResult:
        """Generate a skill folder from extraction results.

        Args:
            extraction: LLM-extracted role, skills, and trait data.
            identity: Validated PersonaNexus AgentIdentity instance.
            jd: Optional parsed job description for additional context.

        Returns:
            SkillFolderResult with skill_name and SKILL.md content.
        """
        skill_name = self._make_skill_name(extraction)

        return SkillFolderResult(
            skill_name=skill_name,
            skill_md=self._render_skill_md(extraction, identity, jd, skill_name),
        )

    # ------------------------------------------------------------------
    # Skill name derivation
    # ------------------------------------------------------------------

    def _make_skill_name(self, extraction: ExtractionResult) -> str:
        """Derive a Claude Code skill slug from the role title.

        Produces lowercase-hyphenated names like 'senior-data-engineer'.
        """
        raw = safe_filename(extraction.role.title).lower().replace("_", "-")
        # Collapse multiple hyphens
        import re
        raw = re.sub(r"-+", "-", raw).strip("-")
        return raw or "generated-skill"

    # ------------------------------------------------------------------
    # SKILL.md rendering (frontmatter + body)
    # ------------------------------------------------------------------

    def _render_skill_md(
        self,
        extraction: ExtractionResult,
        identity: Any,
        jd: JobDescription | None,
        skill_name: str,
    ) -> str:
        """Build the complete SKILL.md with YAML frontmatter + markdown body."""
        lines: list[str] = []

        # YAML frontmatter
        self._render_frontmatter(lines, extraction, skill_name)

        # Markdown body (instructions for Claude)
        self._render_body(lines, extraction, identity, jd)

        return "\n".join(lines)

    def _render_frontmatter(
        self,
        lines: list[str],
        extraction: ExtractionResult,
        skill_name: str,
    ) -> None:
        """Render YAML frontmatter block."""
        # Build description from purpose, truncated for frontmatter
        description = extraction.role.purpose
        if len(description) > 200:
            description = description[:197] + "..."

        lines.append("---")
        lines.append(f"name: {skill_name}")
        lines.append(f"description: {description}")

        # Build trigger hint from primary scope
        if extraction.role.scope_primary:
            hint = extraction.role.scope_primary[0]
            if len(hint) > 60:
                hint = hint[:57] + "..."
            lines.append(f"argument-hint: \"[{hint}]\"")

        # Default allowed tools for Claude Code
        lines.append("allowed-tools: Read, Grep, Glob, Bash, Write, Edit")

        lines.append("---")
        lines.append("")

    def _render_body(
        self,
        lines: list[str],
        extraction: ExtractionResult,
        identity: Any,
        jd: JobDescription | None,
    ) -> None:
        """Render the markdown body (instructions for Claude)."""
        self._render_header(lines, extraction)
        self._render_identity(lines, extraction)
        self._render_triggers(lines, extraction)
        self._render_competencies(lines, extraction)
        self._render_workflows(lines, extraction)
        self._render_scope(lines, extraction)
        self._render_audience(lines, extraction)
        self._render_footer(lines, extraction, jd)

    def _render_header(
        self, lines: list[str], extraction: ExtractionResult
    ) -> None:
        """Render title and purpose."""
        lines.append(f"# {extraction.role.title}")
        lines.append("")
        lines.append(f"> {extraction.role.purpose}")
        lines.append("")

    def _render_identity(
        self, lines: list[str], extraction: ExtractionResult
    ) -> None:
        """Render identity statement, personality, and communication style."""
        lines.append("## Identity & Personality")
        lines.append("")
        lines.append(
            f"You are a {extraction.role.seniority.value}-level "
            f"{extraction.role.title} specializing in {extraction.role.domain}."
        )
        lines.append("")

        defined = extraction.suggested_traits.defined_traits()
        if defined:
            sorted_traits = sorted(defined.items(), key=lambda x: x[1], reverse=True)

            for trait_name, value in sorted_traits:
                display_name = trait_name.replace("_", " ").title()
                desc = _trait_description(trait_name, value)
                prompt = _trait_prompt(trait_name)
                line = f"- **{display_name}** ({value:.0%}): {desc}"
                if prompt:
                    line += f". {prompt}."
                lines.append(line)
            lines.append("")

            # Communication style
            lines.append("### Communication Style")
            lines.append("")
            style_notes = self._derive_communication_style(defined)
            for note in style_notes:
                lines.append(f"- {note}")
            lines.append("")

    def _derive_communication_style(self, traits: dict[str, float]) -> list[str]:
        """Derive communication style notes from trait combinations."""
        notes: list[str] = []

        rigor = traits.get("rigor", 0.5)
        directness = traits.get("directness", 0.5)
        warmth = traits.get("warmth", 0.5)
        verbosity = traits.get("verbosity", 0.5)
        patience = traits.get("patience", 0.5)

        if rigor >= 0.65 and directness >= 0.65:
            notes.append("Be precise and straightforward in all communications")
        elif rigor >= 0.65:
            notes.append("Prioritize accuracy and detail in responses")
        elif directness >= 0.65:
            notes.append("Be clear and direct, avoiding unnecessary hedging")

        if warmth >= 0.65:
            notes.append("Maintain a warm, approachable tone")
        elif warmth < 0.35:
            notes.append("Keep communications professional and objective")

        if verbosity >= 0.65:
            notes.append("Provide thorough explanations with supporting detail")
        elif verbosity < 0.35:
            notes.append("Keep responses concise and focused on key points")

        if patience >= 0.65:
            notes.append("Take time to explain concepts step by step when needed")

        if not notes:
            notes.append("Use a balanced, professional communication style")

        return notes

    def _render_triggers(
        self, lines: list[str], extraction: ExtractionResult
    ) -> None:
        """Render trigger patterns from scope and responsibilities."""
        triggers: list[str] = list(extraction.role.scope_primary)

        for resp in extraction.responsibilities[:3]:
            trigger = resp.split(",")[0].strip()
            if trigger and trigger not in triggers:
                triggers.append(trigger)

        if not triggers:
            return

        lines.append("## When to Use This Skill")
        lines.append("")
        lines.append("Activate this skill when the user's request involves:")
        lines.append("")
        for trigger in triggers:
            lines.append(f"- {trigger}")
        lines.append("")

    def _render_competencies(
        self, lines: list[str], extraction: ExtractionResult
    ) -> None:
        """Render core competencies: domain, technical, tools."""
        lines.append("## Core Competencies")
        lines.append("")

        # Domain expertise
        domain_skills = [
            s for s in extraction.skills if s.category == SkillCategory.DOMAIN
        ]
        if domain_skills:
            lines.append("### Domain Expertise")
            lines.append("")
            for skill in domain_skills:
                lines.append(f"- **{skill.name}**: {skill.context or skill.name}")
                if skill.genai_application:
                    lines.append(f"  - GenAI integration: {skill.genai_application}")
            lines.append("")

        # Technical skills
        hard_skills = [
            s for s in extraction.skills if s.category == SkillCategory.HARD
        ]
        if hard_skills:
            lines.append("### Technical Skills")
            lines.append("")
            for skill in hard_skills:
                prof = skill.proficiency.value
                lines.append(f"- **{skill.name}** ({prof})")
                if skill.context:
                    lines.append(f"  - {skill.context}")
                if skill.examples:
                    lines.append(f"  - Tools: {', '.join(skill.examples)}")
                if skill.genai_application:
                    lines.append(f"  - GenAI integration: {skill.genai_application}")
            lines.append("")

        # Tools & platforms
        tool_skills = [
            s for s in extraction.skills if s.category == SkillCategory.TOOL
        ]
        if tool_skills:
            lines.append("### Tools & Platforms")
            lines.append("")
            for skill in tool_skills:
                prof = skill.proficiency.value
                lines.append(f"- **{skill.name}** ({prof})")
                if skill.context:
                    lines.append(f"  - {skill.context}")
                if skill.examples:
                    lines.append(f"  - Components: {', '.join(skill.examples)}")
                if skill.genai_application:
                    lines.append(f"  - GenAI integration: {skill.genai_application}")
            lines.append("")

    def _render_workflows(
        self, lines: list[str], extraction: ExtractionResult
    ) -> None:
        """Render workflows derived from responsibilities."""
        if not extraction.responsibilities:
            return

        tool_names = [
            s.name
            for s in extraction.skills
            if s.category in (SkillCategory.TOOL, SkillCategory.HARD)
        ]

        lines.append("## Workflows")
        lines.append("")

        for i, resp in enumerate(extraction.responsibilities, 1):
            lines.append(f"### Workflow {i}: {resp}")
            lines.append("")
            lines.append(f"When asked to {resp.lower()}, follow these steps:")
            lines.append("")
            lines.append("1. Clarify requirements and gather context from the user")
            lines.append("2. Assess the current state and identify key considerations")
            lines.append(f"3. {resp}")
            if tool_names:
                tools_str = ", ".join(tool_names[:3])
                lines.append(
                    f"4. Leverage relevant tools ({tools_str}) as appropriate"
                )
                lines.append("5. Review output and validate against requirements")
                lines.append("6. Document findings and provide clear summary")
            else:
                lines.append("4. Review output and validate against requirements")
                lines.append("5. Document findings and provide clear summary")
            lines.append("")

    def _render_scope(
        self, lines: list[str], extraction: ExtractionResult
    ) -> None:
        """Render scope and boundaries."""
        lines.append("## Scope & Boundaries")
        lines.append("")

        if extraction.role.scope_primary:
            lines.append("### In Scope")
            lines.append("")
            for item in extraction.role.scope_primary:
                lines.append(f"- {item}")
            lines.append("")

        if extraction.role.scope_secondary:
            lines.append("### Secondary (Defer When Possible)")
            lines.append("")
            for item in extraction.role.scope_secondary:
                lines.append(f"- {item}")
            lines.append("")

        # Guardrails
        lines.append("### Guardrails")
        lines.append("")
        lines.append(f"- Stay within {extraction.role.domain} domain expertise")
        lines.append(
            "- Acknowledge limitations in areas outside core competencies"
        )

        soft_skills = [
            s for s in extraction.skills if s.category == SkillCategory.SOFT
        ]
        if soft_skills:
            soft_names = ", ".join(s.name.lower() for s in soft_skills)
            lines.append(
                f"- Defer to human judgment for areas requiring {soft_names}"
            )
        lines.append("")

    def _render_audience(
        self, lines: list[str], extraction: ExtractionResult
    ) -> None:
        """Render audience section."""
        if not extraction.role.audience:
            return

        lines.append("## Audience")
        lines.append("")
        lines.append("This agent is designed to interact with:")
        lines.append("")
        for audience in extraction.role.audience:
            lines.append(f"- {audience}")
        lines.append("")

    def _render_footer(
        self,
        lines: list[str],
        extraction: ExtractionResult,
        jd: JobDescription | None,
    ) -> None:
        """Render metadata footer."""
        source_info = "Unknown"
        if jd:
            source_info = jd.title
            if jd.company:
                source_info += f" at {jd.company}"

        lines.append("---")
        lines.append(
            f"*Generated by AgentForge | "
            f"Source: {source_info} | "
            f"{datetime.now(timezone.utc).strftime('%Y-%m-%d')}*"
        )
        lines.append("")
