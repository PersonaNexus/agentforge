"""Gap analysis: compare generated agent capabilities against JD requirements."""

from __future__ import annotations

from typing import Any

from agentforge.models.extracted_skills import (
    ExtractionResult,
    SkillCategory,
    SkillImportance,
    SkillProficiency,
)

# Shared weight tables — single source of truth for both basic and deep analysis.
IMPORTANCE_WEIGHTS: dict[SkillImportance, float] = {
    SkillImportance.REQUIRED: 1.0,
    SkillImportance.PREFERRED: 0.5,
    SkillImportance.NICE_TO_HAVE: 0.2,
}

PRIORITY_LABELS: dict[SkillImportance, str] = {
    SkillImportance.REQUIRED: "critical",
    SkillImportance.PREFERRED: "high",
    SkillImportance.NICE_TO_HAVE: "low",
}

# Automation coverage by category — soft skills are harder to automate.
_CATEGORY_BASE_SCORES: dict[SkillCategory, float] = {
    SkillCategory.HARD: 0.85,
    SkillCategory.TOOL: 0.90,
    SkillCategory.DOMAIN: 0.75,
    SkillCategory.SOFT: 0.40,
}

# Proficiency multiplier — higher proficiency requirements are harder to meet.
_PROFICIENCY_MULTIPLIERS: dict[SkillProficiency, float] = {
    SkillProficiency.BEGINNER: 1.0,
    SkillProficiency.INTERMEDIATE: 0.95,
    SkillProficiency.ADVANCED: 0.85,
    SkillProficiency.EXPERT: 0.70,
}

# Keywords in responsibilities that signal need for human judgment.
_HUMAN_KEYWORDS = [
    "mentor", "lead", "negotiate", "present", "interview",
    "hire", "fire", "counsel", "coach", "empathize",
    "relationship", "stakeholder", "executive",
]


def _skill_coverage_score(category: SkillCategory, proficiency: SkillProficiency) -> float:
    """Compute a nuanced coverage score for a single skill.

    Considers both the skill category (soft skills harder to automate) and
    the required proficiency level (expert-level requirements are harder to
    satisfy than beginner-level).
    """
    base = _CATEGORY_BASE_SCORES.get(category, 0.75)
    multiplier = _PROFICIENCY_MULTIPLIERS.get(proficiency, 0.95)
    return round(base * multiplier, 2)


class GapAnalyzer:
    """Analyzes coverage gaps between a generated agent and the source JD."""

    def analyze(self, extraction: ExtractionResult) -> tuple[float, list[str]]:
        """Compute coverage score and identify gaps.

        Returns:
            Tuple of (coverage_score 0-1, list of gap descriptions)
        """
        gaps: list[str] = []
        total_weight = 0.0
        covered_weight = 0.0

        # Assess skill coverage
        for skill in extraction.skills:
            weight = IMPORTANCE_WEIGHTS.get(skill.importance, 0.5)
            total_weight += weight

            score = _skill_coverage_score(skill.category, skill.proficiency)
            covered_weight += weight * score

            # Flag soft skills that are required
            if skill.category == SkillCategory.SOFT and skill.importance == SkillImportance.REQUIRED:
                gaps.append(
                    f"Soft skill '{skill.name}' may require human judgment"
                )

        # Assess responsibility coverage
        responsibility_weight = 0.3  # each responsibility
        for resp in extraction.responsibilities:
            total_weight += responsibility_weight
            resp_lower = resp.lower()

            if any(kw in resp_lower for kw in _HUMAN_KEYWORDS):
                covered_weight += responsibility_weight * 0.3
                gaps.append(f"Responsibility requires human element: '{resp[:60]}'")
            else:
                covered_weight += responsibility_weight * 0.7

        # Compute coverage
        coverage = covered_weight / total_weight if total_weight > 0 else 0.0
        coverage = round(min(1.0, coverage), 2)

        return coverage, gaps

    def detailed_analyze(
        self, extraction: ExtractionResult
    ) -> tuple[float, list[str], list[dict[str, Any]]]:
        """Deep analysis with per-skill scoring and priority ranking.

        Uses category-aware base scores and proficiency-level multipliers to
        produce differentiated scores per skill, rather than flat heuristics.

        Returns:
            Tuple of (coverage_score, gap_descriptions, skill_scores)
            where skill_scores is a list of dicts with skill, score, priority, etc.
        """
        coverage, gaps = self.analyze(extraction)

        skill_scores: list[dict[str, Any]] = []
        for skill in extraction.skills:
            score = _skill_coverage_score(skill.category, skill.proficiency)

            skill_scores.append({
                "skill": skill.name,
                "category": skill.category.value,
                "proficiency": skill.proficiency.value,
                "score": score,
                "weight": IMPORTANCE_WEIGHTS.get(skill.importance, 0.5),
                "priority": PRIORITY_LABELS.get(skill.importance, "medium"),
                "context": skill.context,
                "genai_application": skill.genai_application,
            })

        # Sort by weight descending, then score ascending (worst coverage first)
        skill_scores.sort(key=lambda x: (-x["weight"], x["score"]))

        return coverage, gaps, skill_scores
