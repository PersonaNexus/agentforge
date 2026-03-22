"""Tests for the skill testing & validation module."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from agentforge.models.extracted_skills import (
    ExtractionResult,
    ExtractedRole,
    ExtractedSkill,
    Heuristic,
    MethodologyExtraction,
    OutputTemplate,
    QualityCriterion,
    SkillCategory,
    SkillProficiency,
    SuggestedTraits,
    TriggerTechniqueMapping,
)
from agentforge.testing.evaluator import Evaluator
from agentforge.testing.models import (
    CriterionScore,
    ScoredExecution,
    TestExecution,
    TestReport,
    TestScenario,
)
from agentforge.testing.scenario_generator import ScenarioGenerator
from agentforge.testing.skill_runner import SkillRunner


def _sample_extraction() -> ExtractionResult:
    return ExtractionResult(
        role=ExtractedRole(
            title="Data Engineer",
            purpose="Build data pipelines",
            scope_primary=["ETL design", "Data modeling"],
            seniority="senior",
            domain="data",
        ),
        skills=[
            ExtractedSkill(
                name="Python", category=SkillCategory.HARD,
                proficiency=SkillProficiency.ADVANCED, importance="required",
                context="Pipeline development",
            ),
        ],
        responsibilities=[
            "Design and implement ETL pipelines",
            "Build data warehouse architecture",
            "Establish data quality frameworks",
        ],
        suggested_traits=SuggestedTraits(rigor=0.85, directness=0.7),
        automation_potential=0.4,
    )


def _sample_methodology() -> MethodologyExtraction:
    return MethodologyExtraction(
        heuristics=[
            Heuristic(
                trigger="When designing a new pipeline",
                procedure="1. Assess data volume\n2. Choose framework\n3. Implement",
            ),
        ],
        trigger_mappings=[
            TriggerTechniqueMapping(
                trigger_pattern="evaluate data quality",
                technique="Run profiling checks",
                output_format="Quality report",
            ),
            TriggerTechniqueMapping(
                trigger_pattern="design ETL pipeline",
                technique="Follow medallion architecture",
            ),
        ],
        quality_criteria=[
            QualityCriterion(criterion="Pipeline handles edge cases"),
            QualityCriterion(criterion="Data types are validated"),
        ],
    )


class TestScenarioGenerator:
    def test_generate_from_triggers(self):
        gen = ScenarioGenerator()
        methodology = _sample_methodology()
        scenarios = gen.generate(_sample_extraction(), methodology)
        trigger_scenarios = [s for s in scenarios if s.source == "trigger"]
        assert len(trigger_scenarios) >= 2  # 2 trigger mappings + 1 heuristic

    def test_generate_from_responsibilities(self):
        gen = ScenarioGenerator()
        scenarios = gen.generate(_sample_extraction())
        resp_scenarios = [s for s in scenarios if s.source == "responsibility"]
        assert len(resp_scenarios) >= 2

    def test_generate_edge_cases(self):
        gen = ScenarioGenerator()
        scenarios = gen.generate(_sample_extraction())
        edge_scenarios = [s for s in scenarios if s.source == "edge_case"]
        assert len(edge_scenarios) >= 1

    def test_max_scenarios(self):
        gen = ScenarioGenerator(max_scenarios=3)
        scenarios = gen.generate(_sample_extraction(), _sample_methodology())
        assert len(scenarios) <= 3

    def test_quality_criteria_attached(self):
        gen = ScenarioGenerator()
        methodology = _sample_methodology()
        scenarios = gen.generate(_sample_extraction(), methodology)
        trigger_scenarios = [s for s in scenarios if s.source == "trigger"]
        for s in trigger_scenarios:
            assert len(s.quality_criteria) > 0

    def test_empty_extraction(self):
        gen = ScenarioGenerator()
        extraction = ExtractionResult(
            role=ExtractedRole(title="Empty", purpose="Nothing", domain="general"),
            skills=[],
            responsibilities=[],
        )
        scenarios = gen.generate(extraction)
        assert len(scenarios) >= 1  # At least edge cases


class TestSkillRunner:
    def test_run_scenarios_with_fallback(self):
        runner = SkillRunner()
        scenario = TestScenario(
            name="test",
            input_prompt="Hello",
        )

        # Mock LLM client — generate() raises AttributeError to trigger fallback
        mock_client = MagicMock(spec=[])  # spec=[] prevents auto-creating attrs
        mock_client._anthropic_client = MagicMock()
        mock_client._openai_client = None
        mock_client.model = "test-model"

        mock_response = MagicMock()
        mock_content = MagicMock()
        mock_content.text = "Test response"
        mock_response.content = [mock_content]
        mock_client._anthropic_client.messages.create.return_value = mock_response

        results = runner.run_scenarios("# Test Skill", [scenario], mock_client)
        assert len(results) == 1
        assert results[0].response == "Test response"
        assert results[0].latency_ms > 0

    def test_run_scenarios_with_generate(self):
        runner = SkillRunner()
        scenario = TestScenario(name="test", input_prompt="Hello")

        mock_client = MagicMock()
        mock_client.generate.return_value = "Generated response"

        results = runner.run_scenarios("# Skill", [scenario], mock_client)
        assert len(results) == 1
        assert results[0].response == "Generated response"


class TestEvaluator:
    def test_evaluate_heuristic(self):
        evaluator = Evaluator()
        execution = TestExecution(
            scenario=TestScenario(
                name="test",
                input_prompt="Design a pipeline",
                quality_criteria=["Should be detailed"],
            ),
            response="Here is a detailed pipeline design with multiple stages and error handling. " * 20,
        )
        report = evaluator.evaluate([execution])
        assert report.overall_score > 0
        assert len(report.scored_executions) == 1

    def test_evaluate_multiple(self):
        evaluator = Evaluator()
        executions = [
            TestExecution(
                scenario=TestScenario(name="good", input_prompt="Q", quality_criteria=["Be relevant"]),
                response="Relevant detailed answer " * 50,
            ),
            TestExecution(
                scenario=TestScenario(name="short", input_prompt="Q", quality_criteria=["Be relevant"]),
                response="OK",
            ),
        ]
        report = evaluator.evaluate(executions)
        assert len(report.scored_executions) == 2
        # Longer response should score higher with heuristic evaluator
        assert report.scored_executions[0].overall_score >= report.scored_executions[1].overall_score

    def test_evaluate_empty(self):
        evaluator = Evaluator()
        report = evaluator.evaluate([])
        assert report.overall_score == 0
        assert report.pass_rate == 0

    def test_report_summary(self):
        report = TestReport(
            scored_executions=[
                ScoredExecution(
                    execution=TestExecution(
                        scenario=TestScenario(name="t", input_prompt="Q"),
                        response="A",
                    ),
                    overall_score=0.8,
                ),
            ],
            overall_score=0.8,
        )
        summary = report.summary()
        assert "1/1" in summary
        assert "100%" in summary

    def test_report_to_dict(self):
        report = TestReport(
            scored_executions=[],
            overall_score=0.5,
            weakest_criteria=["criterion A"],
            recommendations=["Fix A"],
        )
        d = report.to_dict()
        assert d["overall_score"] == 0.5
        assert "criterion A" in d["weakest_criteria"]
        assert "summary" in d


class TestTestModels:
    def test_scenario_to_dict(self):
        s = TestScenario(name="test", input_prompt="hello", source="trigger")
        d = s.to_dict()
        assert d["name"] == "test"
        assert d["source"] == "trigger"

    def test_execution_to_dict(self):
        e = TestExecution(
            scenario=TestScenario(name="t", input_prompt="q"),
            response="a",
            tokens_used=100,
        )
        d = e.to_dict()
        assert d["tokens_used"] == 100

    def test_pass_rate(self):
        report = TestReport(
            scored_executions=[
                ScoredExecution(
                    execution=TestExecution(
                        scenario=TestScenario(name="pass", input_prompt="q"),
                        response="a",
                    ),
                    overall_score=0.8,
                ),
                ScoredExecution(
                    execution=TestExecution(
                        scenario=TestScenario(name="fail", input_prompt="q"),
                        response="a",
                    ),
                    overall_score=0.3,
                ),
            ],
            overall_score=0.55,
        )
        assert report.pass_rate == 0.5
