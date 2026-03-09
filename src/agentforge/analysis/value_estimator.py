"""Agent value estimator: estimate the dollar value an AI agent delivers for a role."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agentforge.models.extracted_skills import (
    ExtractionResult,
    SkillCategory,
    SkillImportance,
    SkillProficiency,
)


# How automatable each skill category is (0-1)
_CATEGORY_WEIGHTS: dict[SkillCategory, float] = {
    SkillCategory.TOOL: 0.90,
    SkillCategory.HARD: 0.75,
    SkillCategory.DOMAIN: 0.60,
    SkillCategory.SOFT: 0.30,
}

# Importance multipliers for weighting skills
_IMPORTANCE_WEIGHTS: dict[SkillImportance, float] = {
    SkillImportance.REQUIRED: 1.0,
    SkillImportance.PREFERRED: 0.6,
    SkillImportance.NICE_TO_HAVE: 0.25,
}

# Higher proficiency requirements are harder to replicate
_PROFICIENCY_DISCOUNTS: dict[SkillProficiency, float] = {
    SkillProficiency.BEGINNER: 0.0,
    SkillProficiency.INTERMEDIATE: 0.05,
    SkillProficiency.ADVANCED: 0.12,
    SkillProficiency.EXPERT: 0.20,
}

# Keywords in responsibilities that signal human-only work
_HUMAN_KEYWORDS = [
    "mentor", "lead", "negotiate", "present", "interview",
    "hire", "fire", "counsel", "coach", "empathize",
    "relationship", "stakeholder", "executive",
]


@dataclass
class ValueEstimate:
    """Result of an agent value estimation."""

    estimated_value: float
    salary_midpoint: float
    base_value: float
    skill_factor: float
    proficiency_discount: float
    human_penalty: float
    availability_bonus: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "estimated_value": round(self.estimated_value),
            "salary_midpoint": round(self.salary_midpoint),
            "base_value": round(self.base_value),
            "skill_factor": round(self.skill_factor, 3),
            "proficiency_discount": round(self.proficiency_discount, 3),
            "human_penalty": round(self.human_penalty, 3),
            "availability_bonus": round(self.availability_bonus, 3),
        }


class AgentValueEstimator:
    """Estimates the annual dollar value an AI agent could deliver for a role."""

    def estimate(
        self,
        extraction: ExtractionResult,
        salary_min: float | None = None,
        salary_max: float | None = None,
    ) -> ValueEstimate | None:
        """Compute estimated agent value based on extraction data and salary.

        Uses salary from arguments first, falls back to extraction fields.
        Returns None if no salary information is available.
        """
        s_min = salary_min or extraction.salary_min
        s_max = salary_max or extraction.salary_max

        if not s_min and not s_max:
            return None

        # Compute salary midpoint
        if s_min and s_max:
            salary_midpoint = (s_min + s_max) / 2
        elif s_min:
            salary_midpoint = s_min
        else:
            salary_midpoint = s_max  # type: ignore[assignment]

        # Base value: salary × automation potential
        automation = extraction.automation_potential or 0.0
        base_value = salary_midpoint * automation

        # Skill factor: weighted average of category automation weights
        skill_factor = self._compute_skill_factor(extraction)

        # Proficiency discount: higher requirements = harder to automate well
        proficiency_discount = self._compute_proficiency_discount(extraction)

        # Human penalty: ratio of human-flagged responsibilities
        human_penalty = self._compute_human_penalty(extraction)

        # Availability bonus: agents work 24/7, scaled by automation potential
        availability_bonus = 1.0 + (automation * 0.3)

        estimated_value = (
            base_value
            * skill_factor
            * (1.0 - proficiency_discount)
            * (1.0 - human_penalty)
            * availability_bonus
        )

        return ValueEstimate(
            estimated_value=max(0.0, estimated_value),
            salary_midpoint=salary_midpoint,
            base_value=base_value,
            skill_factor=skill_factor,
            proficiency_discount=proficiency_discount,
            human_penalty=human_penalty,
            availability_bonus=availability_bonus,
        )

    def _compute_skill_factor(self, extraction: ExtractionResult) -> float:
        """Weighted average of skill category automation weights."""
        if not extraction.skills:
            return 0.5  # neutral default

        total_weight = 0.0
        weighted_sum = 0.0

        for skill in extraction.skills:
            importance = _IMPORTANCE_WEIGHTS.get(skill.importance, 0.5)
            category_weight = _CATEGORY_WEIGHTS.get(skill.category, 0.5)
            total_weight += importance
            weighted_sum += importance * category_weight

        return weighted_sum / total_weight if total_weight > 0 else 0.5

    def _compute_proficiency_discount(self, extraction: ExtractionResult) -> float:
        """Average proficiency discount across skills."""
        if not extraction.skills:
            return 0.0

        total = sum(
            _PROFICIENCY_DISCOUNTS.get(s.proficiency, 0.05)
            for s in extraction.skills
        )
        return total / len(extraction.skills)

    def _compute_human_penalty(self, extraction: ExtractionResult) -> float:
        """Fraction of responsibilities that require human judgment, scaled."""
        if not extraction.responsibilities:
            return 0.0

        human_count = sum(
            1
            for r in extraction.responsibilities
            if any(kw in r.lower() for kw in _HUMAN_KEYWORDS)
        )

        ratio = human_count / len(extraction.responsibilities)
        # Scale the penalty: 50% of responsibilities being human = 25% penalty
        return ratio * 0.5
