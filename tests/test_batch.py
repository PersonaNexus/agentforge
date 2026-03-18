"""Tests for the batch processing module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agentforge.models.blueprint import AgentBlueprint
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
from agentforge.pipeline.batch import BatchProcessor, BatchResult
from agentforge.pipeline.forge_pipeline import ForgePipeline


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


def _mock_extraction(title: str = "Test Agent") -> ExtractionResult:
    return ExtractionResult(
        role=ExtractedRole(
            title=title,
            purpose="Test purpose",
            scope_primary=["Testing"],
            audience=["Users"],
            seniority="mid",
            domain="engineering",
        ),
        skills=[
            ExtractedSkill(
                name="Python", category=SkillCategory.HARD,
                proficiency=SkillProficiency.ADVANCED, importance="required",
                context="Primary language",
            ),
        ],
        responsibilities=["Build software"],
        suggested_traits=SuggestedTraits(rigor=0.7),
        automation_potential=0.4,
        automation_rationale="Partially automatable",
    )


class TestBatchResult:
    def test_success_result(self):
        bp = MagicMock(spec=AgentBlueprint)
        result = BatchResult(input_path="test.txt", blueprint=bp, duration=1.5)
        assert result.success is True
        assert result.duration == 1.5

    def test_failure_result(self):
        result = BatchResult(input_path="test.txt", error="Something broke", duration=0.5)
        assert result.success is False
        assert result.error == "Something broke"

    def test_default_values(self):
        result = BatchResult(input_path="test.txt")
        assert result.success is False  # no blueprint
        assert result.error is None
        assert result.duration == 0.0


class TestBatchProcessor:
    def test_process_single_success(self, fixtures_dir, tmp_path):
        """Process a single file successfully."""
        mock_extractor = MagicMock()
        mock_extractor.extract.return_value = _mock_extraction()

        pipeline = ForgePipeline.default()
        processor = BatchProcessor(pipeline=pipeline, output_dir=tmp_path)

        result = processor._process_single(
            str(fixtures_dir / "senior_data_engineer.txt"),
            {"extractor": mock_extractor, "methodology_extractor": _mock_methodology_extractor(), "tool_mapper": _mock_tool_mapper()},
        )

        assert result.success
        assert result.blueprint is not None
        assert result.duration > 0

    def test_process_single_creates_files(self, fixtures_dir, tmp_path):
        """Process a single file and verify output files are created."""
        mock_extractor = MagicMock()
        mock_extractor.extract.return_value = _mock_extraction("Data Engineer")

        pipeline = ForgePipeline.default()
        processor = BatchProcessor(pipeline=pipeline, output_dir=tmp_path)

        result = processor._process_single(
            str(fixtures_dir / "senior_data_engineer.txt"),
            {"extractor": mock_extractor, "methodology_extractor": _mock_methodology_extractor(), "tool_mapper": _mock_tool_mapper()},
        )

        assert result.success
        # Check output files exist
        yaml_files = list(tmp_path.glob("*.yaml"))
        assert len(yaml_files) >= 1
        skill_files = list(tmp_path.glob("*_SKILL.md"))
        assert len(skill_files) >= 1

    def test_process_single_error(self, tmp_path):
        """Process should handle errors gracefully."""
        pipeline = ForgePipeline.default()
        processor = BatchProcessor(pipeline=pipeline, output_dir=tmp_path)

        result = processor._process_single(
            "/nonexistent/file.txt",
            {},
        )

        assert not result.success
        assert result.error is not None
        assert result.duration > 0

    def test_process_batch_sequential(self, fixtures_dir, tmp_path):
        """Process multiple files sequentially."""
        mock_extractor = MagicMock()
        mock_extractor.extract.return_value = _mock_extraction()

        pipeline = ForgePipeline.default()
        processor = BatchProcessor(pipeline=pipeline, parallel=1, output_dir=tmp_path)

        jd_files = [
            str(fixtures_dir / "senior_data_engineer.txt"),
            str(fixtures_dir / "customer_success_manager.txt"),
        ]

        results = processor.process(jd_files, shared_context={"extractor": mock_extractor, "methodology_extractor": _mock_methodology_extractor(), "tool_mapper": _mock_tool_mapper()}, show_progress=False)

        assert len(results) == 2
        assert all(r.success for r in results)

    def test_process_batch_parallel(self, fixtures_dir, tmp_path):
        """Process multiple files in parallel."""
        mock_extractor = MagicMock()
        mock_extractor.extract.return_value = _mock_extraction()

        pipeline = ForgePipeline.default()
        processor = BatchProcessor(pipeline=pipeline, parallel=2, output_dir=tmp_path)

        jd_files = [
            str(fixtures_dir / "senior_data_engineer.txt"),
            str(fixtures_dir / "customer_success_manager.txt"),
            str(fixtures_dir / "ml_research_scientist.txt"),
        ]

        results = processor.process(jd_files, shared_context={"extractor": mock_extractor, "methodology_extractor": _mock_methodology_extractor(), "tool_mapper": _mock_tool_mapper()}, show_progress=False)

        assert len(results) == 3
        assert all(r.success for r in results)

    def test_process_mixed_results(self, fixtures_dir, tmp_path):
        """Process with mix of successes and failures."""
        mock_extractor = MagicMock()
        mock_extractor.extract.return_value = _mock_extraction()

        pipeline = ForgePipeline.default()
        processor = BatchProcessor(pipeline=pipeline, output_dir=tmp_path)

        jd_files = [
            str(fixtures_dir / "senior_data_engineer.txt"),
            "/nonexistent/file.txt",
        ]

        results = processor.process(jd_files, shared_context={"extractor": mock_extractor, "methodology_extractor": _mock_methodology_extractor(), "tool_mapper": _mock_tool_mapper()}, show_progress=False)

        assert len(results) == 2
        successes = [r for r in results if r.success]
        failures = [r for r in results if not r.success]
        assert len(successes) == 1
        assert len(failures) == 1

    def test_output_dir_created(self, fixtures_dir, tmp_path):
        """Output directory should be created if it doesn't exist."""
        output = tmp_path / "nested" / "output"
        mock_extractor = MagicMock()
        mock_extractor.extract.return_value = _mock_extraction()

        processor = BatchProcessor(output_dir=output)
        results = processor.process(
            [str(fixtures_dir / "senior_data_engineer.txt")],
            shared_context={"extractor": mock_extractor, "methodology_extractor": _mock_methodology_extractor(), "tool_mapper": _mock_tool_mapper()},
            show_progress=False,
        )

        assert output.exists()
        assert len(results) == 1

    def test_display_summary(self, capsys):
        """Display summary should print table without errors."""
        bp_mock = MagicMock()
        bp_mock.extraction.role.title = "Test Agent"
        bp_mock.extraction.skills = []
        bp_mock.coverage_score = 0.8

        results = [
            BatchResult(input_path="good.txt", blueprint=bp_mock, duration=2.3),
            BatchResult(input_path="bad.txt", error="Parse failed", duration=0.1),
        ]

        BatchProcessor.display_summary(results)
        # Just verify it runs without error — Rich output goes to console

    def test_parallel_min_one(self):
        """Parallel workers should be at least 1."""
        processor = BatchProcessor(parallel=0)
        assert processor.parallel == 1

        processor2 = BatchProcessor(parallel=-5)
        assert processor2.parallel == 1
