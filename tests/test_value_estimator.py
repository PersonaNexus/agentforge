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
