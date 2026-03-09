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

# --- Token cost estimation constants ---

# Estimated daily interactions by category (calls/day the agent would make)
_CATEGORY_DAILY_INTERACTIONS: dict[SkillCategory, int] = {
    SkillCategory.TOOL: 80,     # High frequency, structured calls
    SkillCategory.HARD: 40,     # Moderate frequency, medium complexity
    SkillCategory.DOMAIN: 20,   # Lower frequency, longer context
    SkillCategory.SOFT: 15,     # Fewest calls, longest conversations
}

# Average tokens per interaction by category
_CATEGORY_TOKENS_PER_CALL: dict[SkillCategory, int] = {
    SkillCategory.TOOL: 800,    # Shorter, structured I/O
    SkillCategory.HARD: 1500,   # Code generation, analysis
    SkillCategory.DOMAIN: 2500, # Long context, domain reasoning
    SkillCategory.SOFT: 3000,   # Extended dialogue, nuance
}

# Proficiency multiplier for token usage (expert work = more complex chains)
_PROFICIENCY_TOKEN_MULTIPLIERS: dict[SkillProficiency, float] = {
    SkillProficiency.BEGINNER: 0.7,
    SkillProficiency.INTERMEDIATE: 1.0,
    SkillProficiency.ADVANCED: 1.3,
    SkillProficiency.EXPERT: 1.6,
}

# Default blended cost per 1K tokens (input + output average, USD)
_DEFAULT_COST_PER_1K_TOKENS = 0.008

# Monthly infrastructure overhead (monitoring, orchestration, maintenance)
_DEFAULT_MONTHLY_INFRA_OVERHEAD = 200.0

# Working days per month
_WORKING_DAYS_PER_MONTH = 22


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

    # Cost modeling fields
    monthly_token_cost: float = 0.0
    monthly_infra_cost: float = 0.0
    monthly_total_cost: float = 0.0
    annual_total_cost: float = 0.0
    net_annual_value: float = 0.0
    roi_multiple: float = 0.0
    payback_months: float = 0.0
    estimated_monthly_tokens: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "estimated_value": round(self.estimated_value),
            "salary_midpoint": round(self.salary_midpoint),
            "base_value": round(self.base_value),
            "skill_factor": round(self.skill_factor, 3),
            "proficiency_discount": round(self.proficiency_discount, 3),
            "human_penalty": round(self.human_penalty, 3),
            "availability_bonus": round(self.availability_bonus, 3),
            "monthly_token_cost": round(self.monthly_token_cost),
            "monthly_infra_cost": round(self.monthly_infra_cost),
            "monthly_total_cost": round(self.monthly_total_cost),
            "annual_total_cost": round(self.annual_total_cost),
            "net_annual_value": round(self.net_annual_value),
            "roi_multiple": round(self.roi_multiple, 1),
            "payback_months": round(self.payback_months, 1),
            "estimated_monthly_tokens": self.estimated_monthly_tokens,
        }


class AgentValueEstimator:
    """Estimates the annual dollar value an AI agent could deliver for a role."""

    def estimate(
        self,
        extraction: ExtractionResult,
        salary_min: float | None = None,
        salary_max: float | None = None,
        cost_per_1k_tokens: float | None = None,
        monthly_infra_override: float | None = None,
    ) -> ValueEstimate | None:
        """Compute estimated agent value based on extraction data and salary.

        Uses salary from arguments first, falls back to extraction fields.
        Returns None if no salary information is available.

        Args:
            cost_per_1k_tokens: Override blended cost per 1K tokens (default $0.008).
            monthly_infra_override: Override monthly infrastructure cost (default $200).
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

        gross_value = max(0.0, estimated_value)

        # Cost modeling
        token_cost_rate = cost_per_1k_tokens if cost_per_1k_tokens is not None else _DEFAULT_COST_PER_1K_TOKENS
        monthly_infra = monthly_infra_override if monthly_infra_override is not None else _DEFAULT_MONTHLY_INFRA_OVERHEAD

        monthly_tokens = self._estimate_monthly_tokens(extraction)
        monthly_token_cost = (monthly_tokens / 1000) * token_cost_rate
        monthly_total_cost = monthly_token_cost + monthly_infra
        annual_total_cost = monthly_total_cost * 12
        net_annual_value = gross_value - annual_total_cost
        roi_multiple = net_annual_value / annual_total_cost if annual_total_cost > 0 else 0.0
        payback_months = annual_total_cost / (gross_value / 12) if gross_value > 0 else 0.0

        return ValueEstimate(
            estimated_value=gross_value,
            salary_midpoint=salary_midpoint,
            base_value=base_value,
            skill_factor=skill_factor,
            proficiency_discount=proficiency_discount,
            human_penalty=human_penalty,
            availability_bonus=availability_bonus,
            monthly_token_cost=monthly_token_cost,
            monthly_infra_cost=monthly_infra,
            monthly_total_cost=monthly_total_cost,
            annual_total_cost=annual_total_cost,
            net_annual_value=net_annual_value,
            roi_multiple=roi_multiple,
            payback_months=payback_months,
            estimated_monthly_tokens=monthly_tokens,
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

    def _estimate_monthly_tokens(self, extraction: ExtractionResult) -> int:
        """Estimate monthly token usage based on skill mix and proficiency."""
        if not extraction.skills:
            # Conservative default: moderate workload
            return 1_000_000

        total_daily_tokens = 0.0
        for skill in extraction.skills:
            daily_calls = _CATEGORY_DAILY_INTERACTIONS.get(skill.category, 30)
            tokens_per_call = _CATEGORY_TOKENS_PER_CALL.get(skill.category, 1500)
            prof_mult = _PROFICIENCY_TOKEN_MULTIPLIERS.get(skill.proficiency, 1.0)
            importance_weight = _IMPORTANCE_WEIGHTS.get(skill.importance, 0.5)

            # Scale interactions by importance (required skills used more)
            daily_tokens = daily_calls * tokens_per_call * prof_mult * importance_weight
            total_daily_tokens += daily_tokens

        # Normalize: don't count each skill as a full workload, use diminishing returns
        # First skill = full weight, additional skills add ~60% each (overlap)
        num_skills = len(extraction.skills)
        if num_skills > 1:
            avg_daily = total_daily_tokens / num_skills
            effective_daily = avg_daily * (1.0 + 0.6 * (num_skills - 1))
        else:
            effective_daily = total_daily_tokens

        # Scale by automation potential (low automation = fewer agent interactions)
        automation = extraction.automation_potential or 0.0
        effective_daily *= max(0.1, automation)

        monthly_tokens = int(effective_daily * _WORKING_DAYS_PER_MONTH)
        return monthly_tokens

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
