"""Tests for all 8 enhancement modules (E1–E8)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.conftest import _make_sample_extraction

from agentforge.models.extracted_skills import (
    ExtractionResult,
    Heuristic,
    MethodologyExtraction,
    OutputTemplate,
    QualityCriterion,
    TriggerTechniqueMapping,
)


def _make_sample_methodology() -> MethodologyExtraction:
    return MethodologyExtraction(
        heuristics=[
            Heuristic(
                trigger="When evaluating data pipeline performance",
                procedure="1. Check throughput 2. Check latency 3. Compare baselines",
                source_responsibility="Monitor pipeline performance",
            ),
        ],
        trigger_mappings=[
            TriggerTechniqueMapping(
                trigger_pattern="Evaluate pipeline",
                technique="Use throughput and latency metrics",
                output_format="Markdown table",
            ),
        ],
        output_templates=[
            OutputTemplate(
                name="Pipeline Report",
                when_to_use="After pipeline evaluation",
                template="# Pipeline Report\n## Throughput\n## Latency",
            ),
        ],
        quality_criteria=[
            QualityCriterion(
                criterion="Includes quantified metrics",
                description="All findings should include measurable data",
            ),
        ],
    )


# ---------------------------------------------------------------------------
# E3: OpenClaw Compiler
# ---------------------------------------------------------------------------


class TestOpenClawCompiler:
    def test_compile_produces_all_files(self):
        from agentforge.generation.openclaw_compiler import OpenClawCompiler

        extraction = _make_sample_extraction()
        methodology = _make_sample_methodology()

        from agentforge.generation.identity_generator import IdentityGenerator

        generator = IdentityGenerator()
        identity, identity_yaml = generator.generate(extraction)

        compiler = OpenClawCompiler()
        output = compiler.compile(
            extraction=extraction,
            identity_yaml=identity_yaml,
            identity=identity,
            methodology=methodology,
        )

        files = output.file_map()
        assert any(k.endswith(".SOUL.md") for k in files)
        assert any(k.endswith(".STYLE.md") for k in files)
        assert any(k.endswith(".personality.json") for k in files)
        assert any(k.endswith(".openclaw.json") for k in files)

    def test_soul_md_contains_identity(self):
        from agentforge.generation.openclaw_compiler import OpenClawCompiler

        extraction = _make_sample_extraction()
        from agentforge.generation.identity_generator import IdentityGenerator

        generator = IdentityGenerator()
        identity, identity_yaml = generator.generate(extraction)

        compiler = OpenClawCompiler()
        output = compiler.compile(
            extraction=extraction,
            identity_yaml=identity_yaml,
            identity=identity,
        )

        assert "Senior Data Engineer" in output.soul_md
        assert "Identity" in output.soul_md
        assert "Guardrails" in output.soul_md

    def test_personality_json_has_traits(self):
        from agentforge.generation.openclaw_compiler import OpenClawCompiler

        extraction = _make_sample_extraction()
        from agentforge.generation.identity_generator import IdentityGenerator

        generator = IdentityGenerator()
        identity, identity_yaml = generator.generate(extraction)

        compiler = OpenClawCompiler()
        output = compiler.compile(
            extraction=extraction,
            identity_yaml=identity_yaml,
            identity=identity,
        )

        data = json.loads(output.personality_json)
        assert "traits" in data
        assert data["traits"]["rigor"] == 0.85

    def test_compile_with_schedule(self):
        from agentforge.generation.openclaw_compiler import OpenClawCompiler

        extraction = _make_sample_extraction()
        from agentforge.generation.identity_generator import IdentityGenerator

        generator = IdentityGenerator()
        identity, identity_yaml = generator.generate(extraction)

        compiler = OpenClawCompiler()
        output = compiler.compile(
            extraction=extraction,
            identity_yaml=identity_yaml,
            identity=identity,
            schedule="0 8 * * *",
        )

        config = json.loads(output.openclaw_json)
        assert config["schedule"] == "0 8 * * *"


# ---------------------------------------------------------------------------
# E4: Cron Agent Template
# ---------------------------------------------------------------------------


class TestCronTemplate:
    def test_cron_config_to_dict(self):
        from agentforge.generation.cron_template import CronConfig

        config = CronConfig(schedule="0 8 * * *")
        d = config.to_dict()
        assert d["schedule"] == "0 8 * * *"
        assert d["context_isolation"] is True

    def test_generate_guardrails(self):
        from agentforge.generation.cron_template import CronTemplateGenerator

        gen = CronTemplateGenerator()
        guardrails = gen.generate_guardrails()
        assert "Context Isolation" in guardrails
        assert "fresh context" in guardrails.lower()

    def test_generate_delivery_template(self):
        from agentforge.generation.cron_template import CronConfig, CronTemplateGenerator

        gen = CronTemplateGenerator()
        config = CronConfig(schedule="0 8 * * *")
        extraction = _make_sample_extraction()
        template = gen.generate_delivery_template(extraction, config)
        assert "Scheduled Report" in template
        assert "0 8 * * *" in template

    def test_enrich_identity_yaml(self):
        from agentforge.generation.cron_template import CronConfig, CronTemplateGenerator

        gen = CronTemplateGenerator()
        config = CronConfig(schedule="0 9 * * MON")
        enriched = gen.enrich_identity_yaml("schema_version: '1.0'\n", config)
        assert "cron_config:" in enriched
        assert "0 9 * * MON" in enriched

    def test_enrich_skill_md(self):
        from agentforge.generation.cron_template import CronConfig, CronTemplateGenerator

        gen = CronTemplateGenerator()
        config = CronConfig()
        extraction = _make_sample_extraction()
        skill_md = "---\nname: test\n---\n\n# Test Agent\n"
        enriched = gen.enrich_skill_md(skill_md, extraction, config)
        assert "Context Isolation" in enriched
        assert "Failure Handling" in enriched


# ---------------------------------------------------------------------------
# E5: Team Validation
# ---------------------------------------------------------------------------


class TestTeamValidator:
    def _make_forged_team(self):
        from agentforge.analysis.team_composer import AgentTeammate
        from agentforge.composition.models import (
            ConductorSkill,
            ForgedTeam,
            ForgedTeammate,
            HandoffProtocol,
        )
        from agentforge.generation.skill_folder import SkillFolderResult

        extraction = _make_sample_extraction()

        tm1 = AgentTeammate(
            name="DataBot",
            archetype="builder",
            arch_key="builder",
            description="Builds data pipelines",
            skills=extraction.skills[:2],
            personality={"rigor": 0.8, "directness": 0.7},
            benefit="Automates pipeline creation",
        )
        tm2 = AgentTeammate(
            name="AnalystBot",
            archetype="analyzer",
            arch_key="analyzer",
            description="Analyzes data quality",
            skills=extraction.skills[2:4],
            personality={"rigor": 0.75, "directness": 0.65},
            benefit="Monitors data quality",
        )

        sf1 = SkillFolderResult(
            skill_name="databot",
            skill_md="# DataBot\nStay within data domain.\nNever fabricate data.\n",
        )
        sf2 = SkillFolderResult(
            skill_name="analystbot",
            skill_md="# AnalystBot\nStay within analytics.\nDon't fabricate results.\n",
        )

        conductor = ConductorSkill(
            skill_name="conductor",
            skill_md="# Conductor",
            routing_table={"DataBot": ["pipeline", "etl"]},
            handoffs=[
                HandoffProtocol(
                    from_agent="conductor",
                    to_agent="DataBot",
                    trigger="pipeline request",
                ),
            ],
        )

        return ForgedTeam(
            role_title="Data Team",
            conductor=conductor,
            teammates=[
                ForgedTeammate(teammate=tm1, identity_yaml="", skill_folder=sf1),
                ForgedTeammate(teammate=tm2, identity_yaml="", skill_folder=sf2),
            ],
        )

    def test_validate_returns_report(self):
        from agentforge.analysis.team_validator import TeamValidator

        team = self._make_forged_team()
        validator = TeamValidator()
        report = validator.validate(team)
        assert report is not None
        assert isinstance(report.passed, bool)

    def test_detects_trait_overlap(self):
        from agentforge.analysis.team_validator import TeamValidator

        team = self._make_forged_team()
        validator = TeamValidator()
        report = validator.validate(team)
        # Both agents have similar personality traits
        overlap_issues = [i for i in report.issues if i.category == "overlap"]
        assert len(overlap_issues) > 0

    def test_detects_routing_gaps(self):
        from agentforge.analysis.team_validator import TeamValidator

        team = self._make_forged_team()
        validator = TeamValidator()
        report = validator.validate(team)
        # AnalystBot not in routing table
        routing_issues = [i for i in report.issues if i.category == "routing"]
        assert any("AnalystBot" in i.message for i in routing_issues)


# ---------------------------------------------------------------------------
# E2: Refinement Loop
# ---------------------------------------------------------------------------


class TestRefinement:
    def test_refinement_result_diff(self):
        from agentforge.refinement.refiner import RefinementResult

        result = RefinementResult(
            original_content="# Old\nSome content\n",
            refined_content="# New\nImproved content\n",
            feedback="make it better",
        )
        diff = result.compute_diff()
        assert "Old" in diff or "New" in diff

    def test_save_refined(self, tmp_path):
        from agentforge.refinement.refiner import RefinementResult, SkillRefiner

        result = RefinementResult(
            original_content="old",
            refined_content="new",
            feedback="test",
        )
        refiner = SkillRefiner()
        out = refiner.save_refined(result, tmp_path, "test-skill")
        assert (out / "SKILL.md").exists()
        assert (out / "SKILL.md").read_text() == "new"
        assert "v2" in out.name


# ---------------------------------------------------------------------------
# E6: Supplement Quality Scoring
# ---------------------------------------------------------------------------


class TestSupplementScorer:
    def test_high_quality_source(self):
        from agentforge.analysis.supplement_scorer import SupplementScorer

        scorer = SupplementScorer()
        text = (
            "When evaluating a pipeline, first check throughput metrics.\n"
            "Then verify latency requirements are met.\n"
            "Ensure data quality standards pass all criteria.\n"
            "The process should always validate against the baseline.\n"
            "Step 1: Gather metrics\nStep 2: Compare baselines\n"
        )
        score = scorer.score_text(text, "runbook.md", ["pipeline", "data", "metrics"])
        assert score.overall_score > 0.4
        assert score.assessment in ("high", "medium")

    def test_low_quality_source(self):
        from agentforge.analysis.supplement_scorer import SupplementScorer

        scorer = SupplementScorer()
        text = "hi\nthanks\nok\nlol\nnice\ncool\n\n\n\n"
        score = scorer.score_text(text, "chat.md")
        assert score.overall_score < 0.4
        assert score.assessment == "low"

    def test_score_multiple_sources(self):
        from agentforge.analysis.supplement_scorer import SupplementScorer

        scorer = SupplementScorer()
        sources = [
            ("good.md", "When evaluating pipelines, always check throughput and latency metrics."),
            ("bad.md", "hi\nthanks\nok\n"),
        ]
        report = scorer.score_sources(sources)
        assert len(report.scores) == 2
        assert report.has_low_quality


# ---------------------------------------------------------------------------
# E7: Drift Detection
# ---------------------------------------------------------------------------


class TestDriftDetector:
    def test_no_drift(self, tmp_path):
        from agentforge.analysis.drift_detector import DriftDetector

        spec = tmp_path / "spec"
        runtime = tmp_path / "runtime"
        spec.mkdir()
        runtime.mkdir()

        (spec / "SKILL.md").write_text("# Agent\nContent")
        (runtime / "SKILL.md").write_text("# Agent\nContent")

        detector = DriftDetector()
        report = detector.detect(spec, runtime)
        # Should have no file_mismatch or content_drift
        assert not report.has_significant_drift

    def test_detect_missing_file(self, tmp_path):
        from agentforge.analysis.drift_detector import DriftDetector

        spec = tmp_path / "spec"
        runtime = tmp_path / "runtime"
        spec.mkdir()
        runtime.mkdir()

        (spec / "SKILL.md").write_text("# Agent")
        (spec / "extra.md").write_text("# Extra")
        (runtime / "SKILL.md").write_text("# Agent")

        detector = DriftDetector()
        report = detector.detect(spec, runtime)
        missing = [f for f in report.findings if "Missing at runtime" in f.description]
        assert len(missing) == 1

    def test_detect_trait_drift(self, tmp_path):
        from agentforge.analysis.drift_detector import DriftDetector

        spec = tmp_path / "spec"
        runtime = tmp_path / "runtime"
        spec.mkdir()
        runtime.mkdir()

        (spec / "personality.json").write_text(
            json.dumps({"traits": {"rigor": 0.85, "warmth": 0.5}})
        )
        (runtime / "personality.json").write_text(
            json.dumps({"traits": {"rigor": 0.60, "warmth": 0.5}})
        )

        detector = DriftDetector()
        report = detector.detect(spec, runtime)
        trait_drifts = report.trait_drifts
        assert len(trait_drifts) >= 1
        assert any("rigor" in f.description for f in trait_drifts)

    def test_detect_added_at_runtime(self, tmp_path):
        from agentforge.analysis.drift_detector import DriftDetector

        spec = tmp_path / "spec"
        runtime = tmp_path / "runtime"
        spec.mkdir()
        runtime.mkdir()

        (spec / "SKILL.md").write_text("# Agent")
        (runtime / "SKILL.md").write_text("# Agent")
        (runtime / "new_guardrail.md").write_text("# New guardrail")

        detector = DriftDetector()
        report = detector.detect(spec, runtime)
        added = [f for f in report.findings if "Added at runtime" in f.description]
        assert len(added) == 1


# ---------------------------------------------------------------------------
# E8: Interview Mode
# ---------------------------------------------------------------------------


class TestInterviewer:
    def test_interview_result_to_role_description(self):
        from agentforge.interview.interviewer import InterviewResult

        result = InterviewResult(
            purpose="Test agent for experiments",
            common_tasks=["Testing prompts", "Validating configs"],
            never_do=["Touch production"],
            domain="testing",
            seniority="mid",
        )
        desc = result.to_role_description()
        assert "Test agent for experiments" in desc
        assert "Testing prompts" in desc
        assert "Touch production" in desc
        assert "testing" in desc


# ---------------------------------------------------------------------------
# Pipeline Integration
# ---------------------------------------------------------------------------


class TestPipelineEnhancements:
    def test_openclaw_pipeline_exists(self):
        from agentforge.pipeline.forge_pipeline import ForgePipeline

        pipeline = ForgePipeline.openclaw()
        stage_names = [s.name for s in pipeline.stages]
        assert "openclaw_compile" in stage_names
        assert "cron_enrich" in stage_names

    def test_cron_pipeline_exists(self):
        from agentforge.pipeline.forge_pipeline import ForgePipeline

        pipeline = ForgePipeline.cron()
        stage_names = [s.name for s in pipeline.stages]
        assert "cron_enrich" in stage_names

    def test_methodology_can_be_skipped(self):
        from agentforge.pipeline.forge_pipeline import ForgePipeline

        pipeline = ForgePipeline.default()
        pipeline.skip_stage("methodology")
        assert "methodology" in pipeline._skipped
