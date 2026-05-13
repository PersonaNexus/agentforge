"""Deterministic smoke tests for the public forge/extract/test CLI loop."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from agentforge.cli import app
from agentforge.models.extracted_skills import (
    ExtractedRole,
    ExtractedSkill,
    ExtractionResult,
    SkillCategory,
    SkillProficiency,
    SuggestedTraits,
)
from agentforge.testing.models import (
    ScoredExecution,
)
from agentforge.testing.models import (
    TestExecution as AgentTestExecution,
)
from agentforge.testing.models import (
    TestReport as AgentTestReport,
)
from agentforge.testing.models import (
    TestScenario as AgentTestScenario,
)

runner = CliRunner()


def _extraction() -> ExtractionResult:
    return ExtractionResult(
        role=ExtractedRole(
            title="Reliability Engineer",
            purpose="Keep agent workflows predictable",
            scope_primary=["Test automation", "Release gates"],
            audience=["Developers"],
            seniority="senior",
            domain="engineering",
        ),
        skills=[
            ExtractedSkill(
                name="Python",
                category=SkillCategory.HARD,
                proficiency=SkillProficiency.ADVANCED,
                importance="required",
                context="Build deterministic tests",
            )
        ],
        responsibilities=["Build tests", "Maintain CI"],
        suggested_traits=SuggestedTraits(rigor=0.9),
        automation_potential=0.6,
        automation_rationale="Well-scoped automation work",
    )


def test_extract_cli_uses_mocked_extractor_without_live_llm(tmp_path):
    jd_file = tmp_path / "job.txt"
    output_file = tmp_path / "extraction.json"
    jd_file.write_text("Reliability Engineer\nRequirements: Python, CI")

    extractor = MagicMock()
    extractor.extract.return_value = _extraction()

    with (
        patch("agentforge.cli._make_client", return_value=MagicMock()) as make_client,
        patch("agentforge.extraction.skill_extractor.SkillExtractor", return_value=extractor),
    ):
        result = runner.invoke(
            app,
            [
                "extract",
                str(jd_file),
                "--format",
                "json",
                "--output",
                str(output_file),
                "--quiet",
            ],
        )

    assert result.exit_code == 0
    assert "Extracted 1 skills" in result.output
    assert '"title": "Reliability Engineer"' in output_file.read_text()
    make_client.assert_called_once()
    extractor.extract.assert_called_once()


def test_forge_cli_uses_mocked_pipeline_without_live_llm(tmp_path):
    jd_file = tmp_path / "job.txt"
    jd_file.write_text("Reliability Engineer\nRequirements: Python, CI")

    identity = SimpleNamespace(metadata=SimpleNamespace(id="reliability-engineer"))
    blueprint = SimpleNamespace(coverage_score=0.75, automation_estimate=0.6)
    pipeline = MagicMock()
    pipeline.run.return_value = {
        "extraction": _extraction(),
        "identity": identity,
        "identity_yaml": "schema_version: '1.0'\n",
        "skill_file": "# Reliability Engineer\n",
    }
    pipeline.to_blueprint.return_value = blueprint

    with (
        patch("agentforge.cli._make_client", return_value=MagicMock()) as make_client,
        patch("agentforge.pipeline.forge_pipeline.ForgePipeline.quick", return_value=pipeline),
    ):
        result = runner.invoke(
            app,
            ["forge", str(jd_file), "--quick", "--output-dir", str(tmp_path)],
        )

    assert result.exit_code == 0
    assert "forged successfully" in result.output
    assert (tmp_path / "reliability-engineer.yaml").exists()
    assert (tmp_path / "reliability-engineer_SKILL.md").exists()
    make_client.assert_called_once()
    pipeline.run.assert_called_once()


def test_test_cli_uses_mocked_pipeline_and_reports_results(tmp_path):
    jd_file = tmp_path / "job.txt"
    jd_file.write_text("Reliability Engineer\nRequirements: Python, CI")

    report = AgentTestReport(
        scored_executions=[
            ScoredExecution(
                execution=AgentTestExecution(
                    scenario=AgentTestScenario(name="pipeline design", input_prompt="Design CI"),
                    response="Use deterministic gates.",
                ),
                overall_score=0.82,
            )
        ],
        overall_score=0.82,
    )
    pipeline = MagicMock()
    pipeline.run.return_value = {"test_report": report}

    with (
        patch("agentforge.cli._make_client", return_value=MagicMock()) as make_client,
        patch("agentforge.pipeline.forge_pipeline.ForgePipeline.default", return_value=pipeline),
    ):
        result = runner.invoke(app, ["test", str(jd_file)])

    assert result.exit_code == 0
    assert "Test Report" in result.output
    assert "pipeline design" in result.output
    assert "82%" in result.output
    make_client.assert_called_once()
    pipeline.add_stage.assert_called_once()
    pipeline.run.assert_called_once()
