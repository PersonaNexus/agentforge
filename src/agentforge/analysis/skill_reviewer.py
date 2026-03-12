"""Skill quality reviewer: identifies actionable gaps in generated skills."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agentforge.models.extracted_skills import (
    ExtractionResult,
    MethodologyExtraction,
    SkillCategory,
)


@dataclass
class SkillGap:
    """A specific, actionable gap in a generated skill."""

    category: str       # methodology, triggers, templates, quality, domain, persona, scope
    title: str          # Human-readable gap title
    description: str    # What's weak and why it matters
    edit_prompt: str    # What the user should provide to fix it
    section: str        # Which SKILL.md section this affects
    priority: str       # high, medium, low

    def to_dict(self) -> dict[str, str]:
        return {
            "category": self.category,
            "title": self.title,
            "description": self.description,
            "edit_prompt": self.edit_prompt,
            "section": self.section,
            "priority": self.priority,
        }


class SkillReviewer:
    """Analyzes generated skill output for actionable gaps.

    Unlike GapAnalyzer (which checks JD coverage), this checks the quality
    of the generated SKILL.md itself — are sections generic, missing, or
    too thin to be useful?
    """

    def review(
        self,
        extraction: ExtractionResult,
        methodology: MethodologyExtraction | None = None,
        has_examples: bool = False,
        has_frameworks: bool = False,
    ) -> list[SkillGap]:
        """Review a generated skill and return actionable gaps.

        Args:
            extraction: The extraction result used to generate the skill.
            methodology: The methodology extraction (may be None or empty).
            has_examples: Whether user provided real-world examples.
            has_frameworks: Whether user provided frameworks/methodologies.

        Returns:
            List of SkillGap objects sorted by priority (high first).
        """
        gaps: list[SkillGap] = []
        meth = methodology or MethodologyExtraction()

        self._check_methodology(gaps, meth, extraction)
        self._check_triggers(gaps, meth)
        self._check_templates(gaps, meth)
        self._check_quality_criteria(gaps, meth)
        self._check_domain_context(gaps, extraction)
        self._check_persona(gaps, extraction)
        self._check_scope(gaps, extraction)
        self._check_examples(gaps, has_examples)
        self._check_frameworks(gaps, has_frameworks)

        priority_order = {"high": 0, "medium": 1, "low": 2}
        gaps.sort(key=lambda g: priority_order.get(g.priority, 9))
        return gaps

    def review_to_dict(
        self,
        extraction: ExtractionResult,
        methodology: MethodologyExtraction | None = None,
        has_examples: bool = False,
        has_frameworks: bool = False,
    ) -> list[dict[str, str]]:
        """Convenience: review and return serializable dicts."""
        return [
            g.to_dict()
            for g in self.review(extraction, methodology, has_examples, has_frameworks)
        ]

    # ------------------------------------------------------------------
    # Individual gap checks
    # ------------------------------------------------------------------

    def _check_methodology(
        self,
        gaps: list[SkillGap],
        meth: MethodologyExtraction,
        extraction: ExtractionResult,
    ) -> None:
        """Check if decision frameworks / heuristics are sufficient."""
        if len(meth.heuristics) < 2:
            resp_sample = ""
            if extraction.responsibilities:
                resp_sample = extraction.responsibilities[0][:80]
            gaps.append(SkillGap(
                category="methodology",
                title="Generic Decision Frameworks",
                description=(
                    f"The skill has {'no' if not meth.heuristics else 'only 1'} "
                    "decision heuristic. Without concrete if/then rules, the agent "
                    "will fall back on generic reasoning instead of your actual "
                    "working patterns."
                ),
                edit_prompt=(
                    "Describe how you actually make decisions in this role. "
                    "For example, when faced with "
                    + (f"'{resp_sample}'" if resp_sample else "a key responsibility")
                    + ", what's your step-by-step thought process? "
                    "What criteria do you use to choose between approaches?"
                ),
                section="Decision Frameworks",
                priority="high",
            ))

    def _check_triggers(
        self, gaps: list[SkillGap], meth: MethodologyExtraction
    ) -> None:
        """Check if trigger → technique mappings are sufficient."""
        if len(meth.trigger_mappings) < 2:
            gaps.append(SkillGap(
                category="triggers",
                title="Weak Trigger Routing",
                description=(
                    f"Only {len(meth.trigger_mappings)} trigger pattern"
                    f"{'s' if len(meth.trigger_mappings) != 1 else ''} defined. "
                    "The agent won't know which technique to apply for different "
                    "types of requests."
                ),
                edit_prompt=(
                    "List the specific types of requests or situations this skill "
                    "should handle, and what approach to use for each. For example: "
                    "'When asked to review code → use the code review checklist', "
                    "'When asked to design a system → use the architecture template'."
                ),
                section="Trigger Router",
                priority="high",
            ))

    def _check_templates(
        self, gaps: list[SkillGap], meth: MethodologyExtraction
    ) -> None:
        """Check if output templates exist."""
        if not meth.output_templates:
            gaps.append(SkillGap(
                category="templates",
                title="Missing Output Templates",
                description=(
                    "No concrete output formats defined. The agent will produce "
                    "unstructured responses instead of following your preferred "
                    "deliverable formats."
                ),
                edit_prompt=(
                    "Paste a real output example or describe the format you "
                    "typically produce. What sections, headings, or structure "
                    "should the output follow? E.g., a report template, review "
                    "format, or analysis framework."
                ),
                section="Output Templates",
                priority="medium",
            ))

    def _check_quality_criteria(
        self, gaps: list[SkillGap], meth: MethodologyExtraction
    ) -> None:
        """Check if quality criteria are defined."""
        if len(meth.quality_criteria) < 2:
            gaps.append(SkillGap(
                category="quality",
                title="Vague Quality Standards",
                description=(
                    f"Only {len(meth.quality_criteria)} quality "
                    f"{'criterion' if len(meth.quality_criteria) == 1 else 'criteria'} "
                    "defined. Without a clear quality bar, the agent can't "
                    "self-evaluate whether its output meets your standards."
                ),
                edit_prompt=(
                    "What does 'done well' look like for this role? List your "
                    "review checklist — the things you'd check before considering "
                    "a deliverable complete. E.g., 'Includes quantified impact', "
                    "'Addresses edge cases', 'Has clear next steps'."
                ),
                section="Quality Standards",
                priority="medium",
            ))

    def _check_domain_context(
        self, gaps: list[SkillGap], extraction: ExtractionResult
    ) -> None:
        """Check if domain skills have GenAI application context."""
        domain_skills = [
            s for s in extraction.skills
            if s.category == SkillCategory.DOMAIN and not s.genai_application
        ]
        if len(domain_skills) >= 2:
            skill_names = ", ".join(s.name for s in domain_skills[:3])
            gaps.append(SkillGap(
                category="domain",
                title="Missing AI Application Context",
                description=(
                    f"Domain skills like {skill_names} lack specific guidance "
                    "on how AI should apply them. The agent will have the skill "
                    "listed but won't know the nuances of using it effectively."
                ),
                edit_prompt=(
                    f"For skills like {skill_names}: How should an AI agent "
                    "apply these specifically? What are the common pitfalls? "
                    "What context or constraints should it keep in mind?"
                ),
                section="Core Competencies",
                priority="low",
            ))

    def _check_persona(
        self, gaps: list[SkillGap], extraction: ExtractionResult
    ) -> None:
        """Check if personality traits are mostly defaults (unset)."""
        defined = extraction.suggested_traits.defined_traits()
        if len(defined) < 3:
            gaps.append(SkillGap(
                category="persona",
                title="Thin Personality Profile",
                description=(
                    f"Only {len(defined)} personality trait"
                    f"{'s' if len(defined) != 1 else ''} explicitly set. "
                    "The agent's communication style will be generic rather "
                    "than matching the role's expected tone."
                ),
                edit_prompt=(
                    "Describe the ideal communication style for this role: "
                    "Should it be formal or casual? Concise or detailed? "
                    "Assertive or collaborative? Humorous or strictly professional? "
                    "Creative or methodical?"
                ),
                section="Identity",
                priority="low",
            ))

    def _check_scope(
        self, gaps: list[SkillGap], extraction: ExtractionResult
    ) -> None:
        """Check if scope boundaries are defined."""
        has_secondary = bool(extraction.role.scope_secondary)
        has_primary = bool(extraction.role.scope_primary)
        if not has_secondary and has_primary:
            gaps.append(SkillGap(
                category="scope",
                title="No Explicit Boundaries",
                description=(
                    "In-scope items are defined but there are no secondary/deferred "
                    "items or explicit boundaries. The agent may overreach into "
                    "areas it shouldn't handle autonomously."
                ),
                edit_prompt=(
                    "What should this agent explicitly NOT do or defer to humans? "
                    "What adjacent areas should it acknowledge but not handle? "
                    "E.g., 'Don't make hiring decisions', 'Defer budget approvals "
                    "to management'."
                ),
                section="Scope & Boundaries",
                priority="low",
            ))

    def _check_examples(
        self, gaps: list[SkillGap], has_examples: bool
    ) -> None:
        """Flag when no real-world examples were provided."""
        if not has_examples:
            gaps.append(SkillGap(
                category="examples",
                title="No Real-World Examples Provided",
                description=(
                    "The skill was generated from the job description alone, "
                    "without real work samples. Providing examples of actual "
                    "deliverables dramatically improves output template quality."
                ),
                edit_prompt=(
                    "Paste a real example of work output for this role — "
                    "an actual report, review, analysis, or deliverable. "
                    "This helps the skill encode your real working patterns "
                    "rather than inferring them."
                ),
                section="Output Templates",
                priority="medium",
            ))

    def _check_frameworks(
        self, gaps: list[SkillGap], has_frameworks: bool
    ) -> None:
        """Flag when no frameworks/methodologies were provided."""
        if not has_frameworks:
            gaps.append(SkillGap(
                category="frameworks",
                title="No Frameworks or Methodologies Specified",
                description=(
                    "No specific frameworks were provided during generation. "
                    "If the role uses particular methodologies (e.g., Agile, "
                    "TOGAF, OWASP, Six Sigma), encoding them makes the skill "
                    "significantly more targeted."
                ),
                edit_prompt=(
                    "What frameworks, methodologies, or established processes "
                    "does this role follow? E.g., 'Agile/Scrum for project "
                    "management', 'OWASP Top 10 for security reviews', "
                    "'STAR method for behavioral assessments'."
                ),
                section="Decision Frameworks",
                priority="medium",
            ))
