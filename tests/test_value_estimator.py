"""Tests for agent value estimator."""

from __future__ import annotations

import pytest

from agentforge.analysis.value_estimator import AgentValueEstimator, ValueEstimate
from agentforge.models.extracted_skills import (
    ExtractionResult,
    ExtractedRole,
    ExtractedSkill,
    SkillCategory,
    SkillImportance,
    SkillProficiency,
)


def _make_role(title: str = "Test") -> ExtractedRole:
    return ExtractedRole(title=title, purpose="Test role", domain="test")


class TestAgentValueEstimator:
    def test_returns_none_without_salary(self):
        result = ExtractionResult(role=_make_role())
        estimator = AgentValueEstimator()
        assert estimator.estimate(result) is None

    def test_basic_estimate_with_salary(self):
        result = ExtractionResult(
            role=_make_role(),
            skills=[
                ExtractedSkill(name="Python", category=SkillCategory.HARD, importance="required"),
            ],
            automation_potential=0.7,
            salary_min=100_000,
            salary_max=150_000,
        )
        estimator = AgentValueEstimator()
        value = estimator.estimate(result)

        assert value is not None
        assert value.salary_midpoint == 125_000
        assert value.estimated_value > 0

    def test_salary_override_takes_precedence(self):
        result = ExtractionResult(
            role=_make_role(),
            skills=[
                ExtractedSkill(name="SQL", category=SkillCategory.HARD, importance="required"),
            ],
            automation_potential=0.5,
            salary_min=50_000,
            salary_max=80_000,
        )
        estimator = AgentValueEstimator()

        # Override with higher salary
        value = estimator.estimate(result, salary_min=200_000, salary_max=250_000)
        assert value is not None
        assert value.salary_midpoint == 225_000

    def test_tool_skills_higher_value_than_soft(self):
        """Roles heavy on tool skills should produce higher agent value."""
        tool_result = ExtractionResult(
            role=_make_role(),
            skills=[
                ExtractedSkill(name="Salesforce", category=SkillCategory.TOOL, importance="required"),
                ExtractedSkill(name="Jira", category=SkillCategory.TOOL, importance="required"),
            ],
            automation_potential=0.7,
            salary_min=100_000,
            salary_max=100_000,
        )
        soft_result = ExtractionResult(
            role=_make_role(),
            skills=[
                ExtractedSkill(name="Leadership", category=SkillCategory.SOFT, importance="required"),
                ExtractedSkill(name="Empathy", category=SkillCategory.SOFT, importance="required"),
            ],
            automation_potential=0.7,
            salary_min=100_000,
            salary_max=100_000,
        )
        estimator = AgentValueEstimator()
        tool_value = estimator.estimate(tool_result)
        soft_value = estimator.estimate(soft_result)

        assert tool_value is not None and soft_value is not None
        assert tool_value.estimated_value > soft_value.estimated_value
        assert tool_value.skill_factor > soft_value.skill_factor

    def test_expert_proficiency_reduces_value(self):
        """Expert-level requirements should reduce estimated value."""
        beginner = ExtractionResult(
            role=_make_role(),
            skills=[
                ExtractedSkill(
                    name="Python", category=SkillCategory.HARD,
                    importance="required", proficiency=SkillProficiency.BEGINNER,
                ),
            ],
            automation_potential=0.7,
            salary_min=100_000,
            salary_max=100_000,
        )
        expert = ExtractionResult(
            role=_make_role(),
            skills=[
                ExtractedSkill(
                    name="Python", category=SkillCategory.HARD,
                    importance="required", proficiency=SkillProficiency.EXPERT,
                ),
            ],
            automation_potential=0.7,
            salary_min=100_000,
            salary_max=100_000,
        )
        estimator = AgentValueEstimator()
        beg_val = estimator.estimate(beginner)
        exp_val = estimator.estimate(expert)

        assert beg_val is not None and exp_val is not None
        assert beg_val.estimated_value > exp_val.estimated_value

    def test_human_responsibilities_reduce_value(self):
        no_human = ExtractionResult(
            role=_make_role(),
            skills=[
                ExtractedSkill(name="Python", category=SkillCategory.HARD, importance="required"),
            ],
            responsibilities=["Write code", "Review PRs", "Deploy services"],
            automation_potential=0.7,
            salary_min=100_000,
            salary_max=100_000,
        )
        with_human = ExtractionResult(
            role=_make_role(),
            skills=[
                ExtractedSkill(name="Python", category=SkillCategory.HARD, importance="required"),
            ],
            responsibilities=["Mentor juniors", "Interview candidates", "Negotiate contracts"],
            automation_potential=0.7,
            salary_min=100_000,
            salary_max=100_000,
        )
        estimator = AgentValueEstimator()
        no_h = estimator.estimate(no_human)
        with_h = estimator.estimate(with_human)

        assert no_h is not None and with_h is not None
        assert no_h.estimated_value > with_h.estimated_value
        assert with_h.human_penalty > no_h.human_penalty

    def test_availability_bonus_scales_with_automation(self):
        low_auto = ExtractionResult(
            role=_make_role(),
            skills=[
                ExtractedSkill(name="X", category=SkillCategory.HARD, importance="required"),
            ],
            automation_potential=0.2,
            salary_min=100_000,
            salary_max=100_000,
        )
        high_auto = ExtractionResult(
            role=_make_role(),
            skills=[
                ExtractedSkill(name="X", category=SkillCategory.HARD, importance="required"),
            ],
            automation_potential=0.9,
            salary_min=100_000,
            salary_max=100_000,
        )
        estimator = AgentValueEstimator()
        low = estimator.estimate(low_auto)
        high = estimator.estimate(high_auto)

        assert low is not None and high is not None
        assert high.availability_bonus > low.availability_bonus

    def test_value_estimate_to_dict(self):
        result = ExtractionResult(
            role=_make_role(),
            skills=[
                ExtractedSkill(name="Python", category=SkillCategory.HARD, importance="required"),
            ],
            automation_potential=0.6,
            salary_min=80_000,
            salary_max=120_000,
        )
        estimator = AgentValueEstimator()
        value = estimator.estimate(result)

        assert value is not None
        d = value.to_dict()
        assert "estimated_value" in d
        assert "salary_midpoint" in d
        assert "skill_factor" in d
        assert "proficiency_discount" in d
        assert "human_penalty" in d
        assert "availability_bonus" in d
        # Cost modeling fields
        assert "monthly_token_cost" in d
        assert "monthly_infra_cost" in d
        assert "monthly_total_cost" in d
        assert "annual_total_cost" in d
        assert "net_annual_value" in d
        assert "roi_multiple" in d
        assert "payback_months" in d
        assert "estimated_monthly_tokens" in d
        assert all(isinstance(v, (int, float)) for v in d.values())

    def test_only_min_salary(self):
        result = ExtractionResult(
            role=_make_role(),
            automation_potential=0.5,
            salary_min=90_000,
        )
        estimator = AgentValueEstimator()
        value = estimator.estimate(result)
        assert value is not None
        assert value.salary_midpoint == 90_000

    def test_only_max_salary(self):
        result = ExtractionResult(
            role=_make_role(),
            automation_potential=0.5,
            salary_max=120_000,
        )
        estimator = AgentValueEstimator()
        value = estimator.estimate(result)
        assert value is not None
        assert value.salary_midpoint == 120_000

    def test_cost_fields_populated(self):
        """Cost modeling fields should be populated with positive values."""
        result = ExtractionResult(
            role=_make_role(),
            skills=[
                ExtractedSkill(name="Python", category=SkillCategory.HARD, importance="required"),
            ],
            automation_potential=0.7,
            salary_min=100_000,
            salary_max=150_000,
        )
        estimator = AgentValueEstimator()
        value = estimator.estimate(result)

        assert value is not None
        assert value.monthly_token_cost > 0
        assert value.monthly_infra_cost > 0
        assert value.monthly_total_cost == value.monthly_token_cost + value.monthly_infra_cost
        assert value.annual_total_cost == value.monthly_total_cost * 12
        assert value.estimated_monthly_tokens > 0

    def test_net_value_is_gross_minus_costs(self):
        """Net annual value should equal gross value minus annual operating costs."""
        result = ExtractionResult(
            role=_make_role(),
            skills=[
                ExtractedSkill(name="Python", category=SkillCategory.HARD, importance="required"),
            ],
            automation_potential=0.7,
            salary_min=100_000,
            salary_max=150_000,
        )
        estimator = AgentValueEstimator()
        value = estimator.estimate(result)

        assert value is not None
        assert abs(value.net_annual_value - (value.estimated_value - value.annual_total_cost)) < 1

    def test_tool_heavy_roles_use_more_tokens(self):
        """Roles with tool skills should have higher token estimates than soft skills."""
        tool_result = ExtractionResult(
            role=_make_role(),
            skills=[
                ExtractedSkill(name="Salesforce", category=SkillCategory.TOOL, importance="required"),
                ExtractedSkill(name="Jira", category=SkillCategory.TOOL, importance="required"),
            ],
            automation_potential=0.7,
            salary_min=100_000,
            salary_max=100_000,
        )
        soft_result = ExtractionResult(
            role=_make_role(),
            skills=[
                ExtractedSkill(name="Leadership", category=SkillCategory.SOFT, importance="required"),
                ExtractedSkill(name="Empathy", category=SkillCategory.SOFT, importance="required"),
            ],
            automation_potential=0.7,
            salary_min=100_000,
            salary_max=100_000,
        )
        estimator = AgentValueEstimator()
        tool_val = estimator.estimate(tool_result)
        soft_val = estimator.estimate(soft_result)

        assert tool_val is not None and soft_val is not None
        assert tool_val.estimated_monthly_tokens > soft_val.estimated_monthly_tokens
        assert tool_val.monthly_token_cost > soft_val.monthly_token_cost

    def test_expert_proficiency_increases_token_cost(self):
        """Expert-level skills should cost more tokens than beginner."""
        beginner = ExtractionResult(
            role=_make_role(),
            skills=[
                ExtractedSkill(
                    name="Python", category=SkillCategory.HARD,
                    importance="required", proficiency=SkillProficiency.BEGINNER,
                ),
            ],
            automation_potential=0.7,
            salary_min=100_000,
            salary_max=100_000,
        )
        expert = ExtractionResult(
            role=_make_role(),
            skills=[
                ExtractedSkill(
                    name="Python", category=SkillCategory.HARD,
                    importance="required", proficiency=SkillProficiency.EXPERT,
                ),
            ],
            automation_potential=0.7,
            salary_min=100_000,
            salary_max=100_000,
        )
        estimator = AgentValueEstimator()
        beg_val = estimator.estimate(beginner)
        exp_val = estimator.estimate(expert)

        assert beg_val is not None and exp_val is not None
        assert exp_val.monthly_token_cost > beg_val.monthly_token_cost

    def test_custom_cost_overrides(self):
        """Custom cost_per_1k_tokens and monthly_infra_override should be respected."""
        result = ExtractionResult(
            role=_make_role(),
            skills=[
                ExtractedSkill(name="Python", category=SkillCategory.HARD, importance="required"),
            ],
            automation_potential=0.7,
            salary_min=100_000,
            salary_max=100_000,
        )
        estimator = AgentValueEstimator()
        default_val = estimator.estimate(result)
        custom_val = estimator.estimate(
            result, cost_per_1k_tokens=0.02, monthly_infra_override=500.0
        )

        assert default_val is not None and custom_val is not None
        assert custom_val.monthly_token_cost > default_val.monthly_token_cost
        assert custom_val.monthly_infra_cost == 500.0
        assert custom_val.annual_total_cost > default_val.annual_total_cost

    def test_roi_and_payback_calculated(self):
        """ROI multiple and payback period should be reasonable for a high-value role."""
        result = ExtractionResult(
            role=_make_role(),
            skills=[
                ExtractedSkill(name="Python", category=SkillCategory.HARD, importance="required"),
            ],
            automation_potential=0.8,
            salary_min=120_000,
            salary_max=180_000,
        )
        estimator = AgentValueEstimator()
        value = estimator.estimate(result)

        assert value is not None
        assert value.roi_multiple > 0
        assert value.payback_months > 0
        assert value.payback_months < 12  # Should pay back within a year for high-value role

    def test_zero_automation_yields_near_zero_value(self):
        result = ExtractionResult(
            role=_make_role(),
            skills=[
                ExtractedSkill(name="X", category=SkillCategory.HARD, importance="required"),
            ],
            automation_potential=0.0,
            salary_min=100_000,
            salary_max=100_000,
        )
        estimator = AgentValueEstimator()
        value = estimator.estimate(result)
        assert value is not None
        assert value.estimated_value == 0.0
