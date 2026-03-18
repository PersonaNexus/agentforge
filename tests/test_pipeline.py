"""Tests for the forge pipeline engine."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from agentforge.models.extracted_skills import (
    ExtractionResult,
    ExtractedRole,
    ExtractedSkill,
    MethodologyExtraction,
    SkillCategory,
    SkillProficiency,
    SuggestedTraits,
)
from agentforge.models.tool_profile import AgentToolProfile
from agentforge.pipeline.forge_pipeline import ForgePipeline
from agentforge.pipeline.stages import (
    AnalyzeStage,
    CultureStage,
    DeepAnalyzeStage,
    ExtractStage,
    GenerateStage,
    IngestStage,
    MapStage,
    MethodologyStage,
    PipelineStage,
)


def _mock_methodology_extractor():
    """Create a mock methodology extractor that returns empty methodology."""
    mock = MagicMock()
    mock.extract.return_value = MethodologyExtraction()
    return mock


def _mock_tool_mapper():
    """Create a mock tool mapper that returns an empty tool profile."""
    mock = MagicMock()
    mock.map_tools.return_value = AgentToolProfile()
    return mock


def _mock_extraction() -> ExtractionResult:
    return ExtractionResult(
        role=ExtractedRole(
            title="Test Engineer",
            purpose="Test software systems",
            scope_primary=["Testing", "QA"],
            audience=["Developers"],
            seniority="mid",
            domain="engineering",
        ),
        skills=[
            ExtractedSkill(
                name="Python", category=SkillCategory.HARD,
                proficiency=SkillProficiency.ADVANCED, importance="required",
                context="Test automation",
            ),
            ExtractedSkill(
                name="Communication", category=SkillCategory.SOFT,
                importance="required", context="Team collaboration",
            ),
        ],
        responsibilities=["Write test cases", "Review code"],
        suggested_traits=SuggestedTraits(rigor=0.8, patience=0.7),
        automation_potential=0.5,
        automation_rationale="Testing is partially automatable",
    )


class TestForgePipeline:
    def test_default_pipeline_stages(self):
        pipeline = ForgePipeline.default()
        names = [s.name for s in pipeline.stages]
        assert names == ["ingest", "anonymize", "extract", "methodology", "map", "culture", "generate", "tool_map", "analyze", "team_compose"]

    def test_quick_pipeline_stages(self):
        pipeline = ForgePipeline.quick()
        names = [s.name for s in pipeline.stages]
        assert names == ["ingest", "anonymize", "extract", "methodology", "generate", "team_compose"]

    def test_skip_stage(self):
        pipeline = ForgePipeline.default()
        pipeline.skip_stage("analyze")

        # Create context that skips the ingest and extract stages too
        # (we'll mock those results)
        context = {"input_path": "test.txt"}

        # Verify analyze is skipped by checking the skipped set
        assert "analyze" in pipeline._skipped

    def test_add_custom_stage(self):
        class CustomStage(PipelineStage):
            name = "custom"
            def run(self, context):
                context["custom_ran"] = True
                return context

        pipeline = ForgePipeline()
        pipeline.add_stage(CustomStage())
        context = pipeline.run({})
        assert context["custom_ran"] is True

    def test_pipeline_with_mocked_extraction(self, fixtures_dir):
        """Test pipeline from ingest through generate with mocked LLM."""
        pipeline = ForgePipeline.default()

        # Create a mock extractor
        mock_extractor = MagicMock()
        mock_extractor.extract.return_value = _mock_extraction()

        context = {
            "input_path": str(fixtures_dir / "senior_data_engineer.txt"),
            "extractor": mock_extractor,
            "methodology_extractor": _mock_methodology_extractor(),
            "tool_mapper": _mock_tool_mapper(),
        }

        context = pipeline.run(context)

        assert "jd" in context
        assert "extraction" in context
        assert "identity" in context
        assert "identity_yaml" in context
        assert "skill_file" in context
        assert "coverage_score" in context
        assert "coverage_gaps" in context

    def test_to_blueprint(self, fixtures_dir):
        """Test blueprint creation from pipeline context."""
        pipeline = ForgePipeline.default()

        mock_extractor = MagicMock()
        mock_extractor.extract.return_value = _mock_extraction()

        context = {
            "input_path": str(fixtures_dir / "senior_data_engineer.txt"),
            "extractor": mock_extractor,
            "methodology_extractor": _mock_methodology_extractor(),
            "tool_mapper": _mock_tool_mapper(),
        }

        context = pipeline.run(context)
        blueprint = pipeline.to_blueprint(context)

        assert blueprint.source_jd is not None
        assert blueprint.extraction.role.title == "Test Engineer"
        assert len(blueprint.identity_yaml) > 0
        assert blueprint.coverage_score > 0
        assert blueprint.automation_estimate == 0.5


class TestStages:
    def test_ingest_stage(self, fixtures_dir):
        stage = IngestStage()
        context = {"input_path": str(fixtures_dir / "senior_data_engineer.txt")}
        result = stage.run(context)
        assert "jd" in result
        assert result["jd"].title

    def test_map_stage(self):
        stage = MapStage()
        context = {"extraction": _mock_extraction()}
        result = stage.run(context)
        assert "traits" in result
        assert isinstance(result["traits"], dict)

    def test_generate_stage(self):
        stage = GenerateStage()
        context = {"extraction": _mock_extraction()}
        result = stage.run(context)
        assert "identity" in result
        assert "identity_yaml" in result
        assert "skill_file" in result

    def test_analyze_stage(self):
        stage = AnalyzeStage()
        context = {"extraction": _mock_extraction()}
        result = stage.run(context)
        assert "coverage_score" in result
        assert "coverage_gaps" in result
        assert 0.0 <= result["coverage_score"] <= 1.0

    def test_deep_analyze_stage(self):
        stage = DeepAnalyzeStage()
        context = {"extraction": _mock_extraction()}
        result = stage.run(context)
        assert "coverage_score" in result
        assert "coverage_gaps" in result
        assert "skill_scores" in result
        assert len(result["skill_scores"]) == 2

    def test_deep_analysis_pipeline(self):
        pipeline = ForgePipeline.deep_analysis()
        names = [s.name for s in pipeline.stages]
        assert "deep_analyze" in names
        assert "analyze" not in names

    def test_deep_analysis_pipeline_full(self, fixtures_dir):
        pipeline = ForgePipeline.deep_analysis()
        mock_extractor = MagicMock()
        mock_extractor.extract.return_value = _mock_extraction()

        context = {
            "input_path": str(fixtures_dir / "senior_data_engineer.txt"),
            "extractor": mock_extractor,
            "methodology_extractor": _mock_methodology_extractor(),
            "tool_mapper": _mock_tool_mapper(),
        }
        context = pipeline.run(context)

        assert "skill_scores" in context
        assert len(context["skill_scores"]) == 2
