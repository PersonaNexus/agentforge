"""Tests for SkillReviewer — skill quality gap analysis."""

from __future__ import annotations

import pytest

from agentforge.analysis.skill_reviewer import SkillGap, SkillReviewer
from agentforge.models.extracted_skills import (
    ExtractionResult,
    ExtractedRole,
    ExtractedSkill,
    Heuristic,
    MethodologyExtraction,
    OutputTemplate,
    QualityCriterion,
    SeniorityLevel,
    SkillCategory,
    SkillImportance,
    SkillProficiency,
    SuggestedTraits,
    TriggerTechniqueMapping,
)


@pytest.fixture
def reviewer() -> SkillReviewer:
    return SkillReviewer()


@pytest.fixture
def minimal_extraction() -> ExtractionResult:
    """Extraction with minimal data — should trigger many gaps."""
    return ExtractionResult(
        role=ExtractedRole(
            title="Analyst",
            purpose="Analyze things",
            scope_primary=["Analysis"],
            seniority=SeniorityLevel.MID,
            domain="Business",
        ),
        skills=[
            ExtractedSkill(
                name="Excel",
                category=SkillCategory.TOOL,
                proficiency=SkillProficiency.ADVANCED,
                importance=SkillImportance.REQUIRED,
            ),
            ExtractedSkill(
                name="Market Research",
                category=SkillCategory.DOMAIN,
                proficiency=SkillProficiency.INTERMEDIATE,
                importance=SkillImportance.REQUIRED,
            ),
            ExtractedSkill(
                name="Financial Modeling",
                category=SkillCategory.DOMAIN,
                proficiency=SkillProficiency.INTERMEDIATE,
                importance=SkillImportance.PREFERRED,
            ),
        ],
        responsibilities=["Analyze market data", "Produce reports"],
        suggested_traits=SuggestedTraits(),  # No traits set
    )


@pytest.fixture
def rich_methodology() -> MethodologyExtraction:
    """Methodology with substantial content — should suppress gaps."""
    return MethodologyExtraction(
        heuristics=[
            Heuristic(trigger="When evaluating data", procedure="Step 1..."),
            Heuristic(trigger="When building reports", procedure="Step 1..."),
            Heuristic(trigger="When validating sources", procedure="Step 1..."),
        ],
        output_templates=[
            OutputTemplate(name="Report", template="## Report\n..."),
        ],
        trigger_mappings=[
            TriggerTechniqueMapping(trigger_pattern="analyze", technique="deep-dive"),
            TriggerTechniqueMapping(trigger_pattern="summarize", technique="executive"),
        ],
        quality_criteria=[
            QualityCriterion(criterion="Data-backed claims"),
            QualityCriterion(criterion="Clear recommendations"),
        ],
    )


class TestSkillGap:
    def test_to_dict(self):
        gap = SkillGap(
            category="test",
            title="Test Gap",
            description="A test",
            edit_prompt="Fix it",
            section="Foo",
            priority="high",
        )
        d = gap.to_dict()
        assert d["category"] == "test"
        assert d["priority"] == "high"
        assert set(d.keys()) == {"category", "title", "description", "edit_prompt", "section", "priority"}


class TestSkillReviewerMaxGaps:
    """Test that minimal input produces the expected gaps."""

    def test_no_methodology_produces_many_gaps(self, reviewer, minimal_extraction):
        gaps = reviewer.review(minimal_extraction)
        categories = {g.category for g in gaps}

        # Should flag all methodology-related gaps
        assert "methodology" in categories
        assert "triggers" in categories
        assert "templates" in categories
        assert "quality" in categories

        # Should flag missing examples and frameworks
        assert "examples" in categories
        assert "frameworks" in categories

        # Minimal extraction has no traits defined
        assert "persona" in categories

    def test_no_scope_secondary_flags_scope(self, reviewer):
        extraction = ExtractionResult(
            role=ExtractedRole(
                title="Tester",
                purpose="Test things",
                scope_primary=["Testing"],
                scope_secondary=[],  # Empty — should trigger
                seniority=SeniorityLevel.JUNIOR,
                domain="QA",
            ),
            skills=[],
            responsibilities=[],
        )
        gaps = reviewer.review(extraction)
        categories = {g.category for g in gaps}
        assert "scope" in categories

    def test_domain_skills_without_genai_flags(self, reviewer, minimal_extraction):
        gaps = reviewer.review(minimal_extraction)
        domain_gap = next((g for g in gaps if g.category == "domain"), None)
        assert domain_gap is not None
        assert "Market Research" in domain_gap.description


class TestSkillReviewerSuppression:
    """Test that rich input suppresses gaps."""

    def test_rich_methodology_suppresses_method_gaps(
        self, reviewer, minimal_extraction, rich_methodology
    ):
        gaps = reviewer.review(
            minimal_extraction,
            methodology=rich_methodology,
            has_examples=True,
            has_frameworks=True,
        )
        categories = {g.category for g in gaps}

        # Rich methodology should suppress these
        assert "methodology" not in categories
        assert "triggers" not in categories
        assert "templates" not in categories
        assert "quality" not in categories

        # User provided examples and frameworks
        assert "examples" not in categories
        assert "frameworks" not in categories

    def test_defined_traits_suppress_persona_gap(self, reviewer):
        extraction = ExtractionResult(
            role=ExtractedRole(
                title="Lead",
                purpose="Lead team",
                seniority=SeniorityLevel.LEAD,
                domain="Engineering",
            ),
            skills=[],
            responsibilities=[],
            suggested_traits=SuggestedTraits(
                warmth=0.8, directness=0.9, rigor=0.7
            ),
        )
        gaps = reviewer.review(extraction)
        categories = {g.category for g in gaps}
        assert "persona" not in categories

    def test_scope_secondary_suppresses_scope_gap(self, reviewer, sample_extraction):
        """sample_extraction has scope_secondary defined."""
        gaps = reviewer.review(sample_extraction)
        categories = {g.category for g in gaps}
        assert "scope" not in categories


class TestSkillReviewerPriority:
    def test_gaps_sorted_by_priority(self, reviewer, minimal_extraction):
        gaps = reviewer.review(minimal_extraction)
        priorities = [g.priority for g in gaps]
        order = {"high": 0, "medium": 1, "low": 2}
        values = [order[p] for p in priorities]
        assert values == sorted(values)


class TestReviewToDict:
    def test_returns_list_of_dicts(self, reviewer, minimal_extraction):
        result = reviewer.review_to_dict(minimal_extraction)
        assert isinstance(result, list)
        assert all(isinstance(d, dict) for d in result)
        assert all("category" in d for d in result)
