"""Generate Claude Code-compatible skill folders from extraction results.

Produces a skill folder containing a single SKILL.md file with YAML
frontmatter and markdown instructions — the exact format Claude Code
expects for drag-and-drop skill installation into .claude/skills/.

The output uses a two-layer structure:
  1. Thin persona layer — who you are (identity, traits, communication style)
  2. Thick methodology layer — how you work (decision frameworks, templates,
     trigger-technique mappings, quality rubrics)

Claude Code skill spec reference:
    .claude/skills/<skill-name>/
    └── SKILL.md   ← YAML frontmatter + markdown body

Frontmatter fields (per Anthropic docs):
    name, description, argument-hint, allowed-tools,
    user-invocable, disable-model-invocation
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from agentforge.models.extracted_skills import (
    ExtractionResult,
    MethodologyExtraction,
    SkillCategory,
)
from agentforge.models.job_description import JobDescription
from agentforge.generation.skill_file import (
    _trait_description,
    _trait_prompt,
)
from agentforge.utils import make_skill_slug, truncate_description


class SkillFolderResult(BaseModel):
    """Container for Claude Code-compatible skill folder content.

    The skill folder maps to .claude/skills/<skill_name>/ and can contain
    SKILL.md plus supplementary reference files (examples, templates, etc.)
    that the skill instructions can reference.
    """

    skill_name: str = Field(..., description="Slug name for the skill folder")
    skill_md: str = Field(..., description="SKILL.md content with YAML frontmatter")
    supplementary_files: dict[str, str] = Field(
        default_factory=dict,
        description="Additional files for the skill folder: {relative_path: content}",
    )


class SkillFolderGenerator:
    """Generates Claude Code-compatible skill folders from extraction results.

    Produces a single SKILL.md with YAML frontmatter metadata and markdown
    instructions, matching the Claude Code skill specification.

    Uses a two-layer structure:
      - Thin persona layer: identity statement, top personality traits,
        communication style (~15 lines)
      - Thick methodology layer: decision frameworks, trigger-technique
        mappings, output templates, quality rubrics (~majority of the doc)
    """

    def generate(
        self,
        extraction: ExtractionResult,
        identity: Any,
        jd: JobDescription | None = None,
        methodology: MethodologyExtraction | None = None,
        user_examples: str = "",
        user_frameworks: str = "",
    ) -> SkillFolderResult:
        """Generate a skill folder from extraction results.

        Args:
            extraction: LLM-extracted role, skills, and trait data.
            identity: Validated PersonaNexus AgentIdentity instance.
            jd: Optional parsed job description for additional context.
            methodology: Optional extracted methodology (heuristics, templates, etc).
            user_examples: Optional user-provided work samples.
            user_frameworks: Optional user-provided frameworks.

        Returns:
            SkillFolderResult with skill_name and SKILL.md content.
        """
        skill_name = self._make_skill_name(extraction)

        return SkillFolderResult(
            skill_name=skill_name,
            skill_md=self._render_skill_md(
                extraction, identity, jd, skill_name,
                methodology, user_examples, user_frameworks,
            ),
        )

    # ------------------------------------------------------------------
    # Skill name derivation
    # ------------------------------------------------------------------

    def _make_skill_name(self, extraction: ExtractionResult) -> str:
        """Derive a Claude Code skill slug from the role title.

        Produces lowercase-hyphenated names like 'senior-data-engineer'.
        Max 64 chars per Anthropic spec.
        """
        return make_skill_slug(extraction.role.title)

    # ------------------------------------------------------------------
    # SKILL.md rendering (frontmatter + body)
    # ------------------------------------------------------------------

    def _render_skill_md(
        self,
        extraction: ExtractionResult,
        identity: Any,
        jd: JobDescription | None,
        skill_name: str,
        methodology: MethodologyExtraction | None,
        user_examples: str,
        user_frameworks: str,
    ) -> str:
        """Build the complete SKILL.md with YAML frontmatter + markdown body."""
        lines: list[str] = []

        # YAML frontmatter
        self._render_frontmatter(lines, extraction, skill_name)

        # Markdown body — two-layer structure
        self._render_body(
            lines, extraction, identity, jd,
            methodology, user_examples, user_frameworks,
        )

        return "\n".join(lines)

    def _render_frontmatter(
        self,
        lines: list[str],
        extraction: ExtractionResult,
        skill_name: str,
    ) -> None:
        """Render YAML frontmatter block per Anthropic skill spec."""
        description = self._build_description(extraction)

        lines.append("---")
        lines.append(f"name: {skill_name}")
        lines.append(f"description: \"{description}\"")

        if extraction.role.scope_primary:
            hint = extraction.role.scope_primary[0]
            if len(hint) > 60:
                hint = hint[:57] + "..."
            lines.append(f"argument-hint: \"[{hint}]\"")

        allowed = self._derive_allowed_tools(extraction)
        lines.append(f"allowed-tools: {', '.join(allowed)}")

        lines.append("---")
        lines.append("")

    def _build_description(self, extraction: ExtractionResult) -> str:
        """Build a rich description with action verbs and keywords."""
        purpose = extraction.role.purpose
        if extraction.responsibilities:
            verbs = []
            for resp in extraction.responsibilities[:3]:
                first_word = resp.split()[0].lower() if resp.split() else ""
                if first_word and first_word not in verbs:
                    verbs.append(first_word)
            if verbs:
                trigger_hint = (
                    f"Use when asked to {', '.join(verbs)} in "
                    f"{extraction.role.domain}. "
                )
                purpose = trigger_hint + purpose

        return truncate_description(purpose).replace('"', '\\"')

    def _derive_allowed_tools(self, extraction: ExtractionResult) -> list[str]:
        """Derive appropriate allowed-tools based on the role's skills."""
        tools = ["Read", "Grep", "Glob"]

        tool_skills = [
            s for s in extraction.skills if s.category == SkillCategory.TOOL
        ]
        hard_skills = [
            s for s in extraction.skills if s.category == SkillCategory.HARD
        ]

        if tool_skills or any(
            kw in extraction.role.domain.lower()
            for kw in ("engineering", "devops", "development", "infrastructure")
        ):
            tools.extend(["Bash", "Write", "Edit"])
        elif hard_skills:
            tools.extend(["Write", "Edit"])

        return tools

    def _render_body(
        self,
        lines: list[str],
        extraction: ExtractionResult,
        identity: Any,
        jd: JobDescription | None,
        methodology: MethodologyExtraction | None,
        user_examples: str,
        user_frameworks: str,
    ) -> None:
        """Render the markdown body with two-layer structure.

        Layer 1 (thin persona): Identity, traits, communication style.
        Layer 2 (thick methodology): Decision frameworks, trigger routing,
        output templates, quality rubrics, competencies.
        """
        self._render_header(lines, extraction)

        # ── Layer 1: Thin persona ──
        self._render_identity(lines, extraction)

        # ── Layer 2: Thick methodology ──
        has_methodology = methodology and methodology.has_content()

        if has_methodology:
            self._render_decision_frameworks(lines, methodology)
            self._render_trigger_router(lines, methodology)
            self._render_output_templates(lines, methodology)
            self._render_quality_standards(lines, methodology)
        else:
            # Fallback to trigger list + generic workflows when methodology is absent
            self._render_triggers(lines, extraction)
            self._render_workflows(lines, extraction)

        self._render_competencies(lines, extraction)
        self._render_scope(lines, extraction)
        self._render_audience(lines, extraction)

        # Quality signal
        self._render_quality_notice(
            lines, has_methodology, user_examples, user_frameworks,
        )

        self._render_arguments_usage(lines)
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
        """Render thin persona layer: identity + top traits + communication style."""
        lines.append("## Identity")
        lines.append("")
        lines.append(
            f"You are a {extraction.role.seniority.value}-level "
            f"{extraction.role.title} specializing in {extraction.role.domain}."
        )
        lines.append("")

        defined = extraction.suggested_traits.defined_traits()
        if defined:
            # Show top traits concisely (not all 10)
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

            # Communication style — brief
            style_notes = self._derive_communication_style(defined)
            lines.append("**Communication style:** " + ". ".join(style_notes) + ".")
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
            notes.append("Be precise and straightforward")
        elif rigor >= 0.65:
            notes.append("Prioritize accuracy and detail")
        elif directness >= 0.65:
            notes.append("Be clear and direct, avoid hedging")

        if warmth >= 0.65:
            notes.append("Maintain a warm, approachable tone")
        elif warmth < 0.35:
            notes.append("Keep communications professional and objective")

        if verbosity >= 0.65:
            notes.append("Provide thorough explanations")
        elif verbosity < 0.35:
            notes.append("Keep responses concise")

        if patience >= 0.65:
            notes.append("Explain step by step when needed")

        if not notes:
            notes.append("Use a balanced, professional communication style")

        return notes

    # ------------------------------------------------------------------
    # Fallback: trigger patterns (when methodology is absent)
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Layer 2: Methodology sections
    # ------------------------------------------------------------------

    def _render_decision_frameworks(
        self, lines: list[str], methodology: MethodologyExtraction
    ) -> None:
        """Render decision frameworks (heuristics) — concrete if/then rules."""
        if not methodology.heuristics:
            return

        lines.append("## Decision Frameworks")
        lines.append("")
        lines.append(
            "Use these concrete decision-making rules when handling requests. "
            "Each framework specifies a trigger situation and the exact procedure to follow."
        )
        lines.append("")

        for i, h in enumerate(methodology.heuristics, 1):
            lines.append(f"### Framework {i}: {h.trigger}")
            lines.append("")
            lines.append(h.procedure)
            lines.append("")

    def _render_trigger_router(
        self, lines: list[str], methodology: MethodologyExtraction
    ) -> None:
        """Render trigger→technique routing table."""
        if not methodology.trigger_mappings:
            return

        lines.append("## Trigger → Technique Router")
        lines.append("")
        lines.append("Match the user's request to the appropriate technique:")
        lines.append("")

        for mapping in methodology.trigger_mappings:
            lines.append(f"**{mapping.trigger_pattern}**")
            lines.append(f"→ *Technique:* {mapping.technique}")
            if mapping.output_format:
                lines.append(f"→ *Output format:* {mapping.output_format}")
            lines.append("")

    def _render_output_templates(
        self, lines: list[str], methodology: MethodologyExtraction
    ) -> None:
        """Render role-specific output scaffolds."""
        if not methodology.output_templates:
            return

        lines.append("## Output Templates")
        lines.append("")
        lines.append(
            "Use these role-specific templates to structure your outputs. "
            "Select the appropriate template based on the request type."
        )
        lines.append("")

        for tmpl in methodology.output_templates:
            lines.append(f"### {tmpl.name}")
            lines.append("")
            if tmpl.when_to_use:
                lines.append(f"*When to use:* {tmpl.when_to_use}")
                lines.append("")
            lines.append("```")
            lines.append(tmpl.template)
            lines.append("```")
            lines.append("")

    def _render_quality_standards(
        self, lines: list[str], methodology: MethodologyExtraction
    ) -> None:
        """Render evaluation criteria — what 'good' looks like."""
        if not methodology.quality_criteria:
            return

        lines.append("## Quality Standards")
        lines.append("")
        lines.append(
            "Every output from this role should meet these criteria. "
            "Use this as a self-evaluation checklist before delivering results."
        )
        lines.append("")

        for criterion in methodology.quality_criteria:
            lines.append(f"- **{criterion.criterion}**")
            if criterion.description:
                lines.append(f"  {criterion.description}")
        lines.append("")

    # ------------------------------------------------------------------
    # Fallback: generic workflows (when methodology is absent)
    # ------------------------------------------------------------------

    def _render_workflows(
        self, lines: list[str], extraction: ExtractionResult
    ) -> None:
        """Render generic workflows from responsibilities (fallback)."""
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

    # ------------------------------------------------------------------
    # Shared sections
    # ------------------------------------------------------------------

    def _render_competencies(
        self, lines: list[str], extraction: ExtractionResult
    ) -> None:
        """Render core competencies: domain, technical, tools."""
        lines.append("## Core Competencies")
        lines.append("")

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

    def _render_quality_notice(
        self,
        lines: list[str],
        has_methodology: bool,
        user_examples: str,
        user_frameworks: str,
    ) -> None:
        """Render quality signal about data completeness."""
        missing: list[str] = []
        if not user_examples.strip():
            missing.append("real-world examples or work samples")
        if not user_frameworks.strip():
            missing.append("specific frameworks or methodologies")
        if not has_methodology:
            missing.append("methodology extraction (decision frameworks, templates)")

        if missing:
            lines.append("> **Skill Quality Note:** This skill was generated without "
                         + ", ".join(missing)
                         + ". Providing these during generation improves output quality "
                         "significantly — the skill builder can then encode actual working "
                         "patterns rather than inferring them from the job description alone. "
                         "Re-run the forge with supplemental data for a more actionable skill.")
            lines.append("")

    def _render_arguments_usage(self, lines: list[str]) -> None:
        """Render $ARGUMENTS usage hint."""
        lines.append("## Usage")
        lines.append("")
        lines.append(
            "This skill accepts optional arguments via `$ARGUMENTS` to "
            "focus on a specific task or area. For example:"
        )
        lines.append("")
        lines.append("- `/<skill-name> review the authentication module`")
        lines.append("- `/<skill-name> draft a migration plan for the database`")
        lines.append("")
        lines.append(
            "When arguments are provided, focus your response on "
            "the specified topic while applying the methodology and "
            "competencies above."
        )
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
