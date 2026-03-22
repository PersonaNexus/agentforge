"""Tests for multi-agent composition and orchestration."""
from __future__ import annotations

import pytest

from agentforge.analysis.team_composer import AgentTeamComposition, AgentTeammate, TeamComposer
from agentforge.composition.conductor_generator import ConductorGenerator
from agentforge.composition.models import (
    ConductorSkill,
    ForgedTeam,
    ForgedTeammate,
    HandoffProtocol,
    OrchestratedWorkflow,
    WorkflowStep,
)
from agentforge.composition.orchestration_config import OrchestrationConfigExporter
from agentforge.composition.team_forger import TeamForger
from agentforge.generation.skill_folder import SkillFolderResult
from agentforge.models.extracted_skills import (
    ExtractionResult,
    ExtractedRole,
    ExtractedSkill,
    Heuristic,
    MethodologyExtraction,
    SkillCategory,
    SkillProficiency,
    SuggestedTraits,
)
from agentforge.pipeline.forge_pipeline import ForgePipeline

from tests.conftest import _make_sample_extraction


class TestTeamForger:
    def test_forge_team(self):
        extraction = _make_sample_extraction()
        composer = TeamComposer()
        team = composer.compose(extraction)

        forger = TeamForger()
        forged = forger.forge_team(team, extraction)

        assert len(forged) == len(team.teammates)
        for ft in forged:
            assert ft.identity_yaml
            assert ft.skill_folder.skill_md
            assert ft.skill_folder.skill_name

    def test_scope_extraction(self):
        extraction = _make_sample_extraction()
        teammate = AgentTeammate(
            name="Test Agent",
            archetype="Technical Builder",
            arch_key="technical_builder",
            description="Handles Python",
            skills=[extraction.skills[0]],  # Python only
            personality={"rigor": 0.9},
            benefit="Builds things",
        )

        forger = TeamForger()
        scoped = forger._scope_extraction(extraction, teammate)

        assert scoped.role.title == "Test Agent"
        assert len(scoped.skills) == 1
        assert scoped.skills[0].name == "Python"

    def test_scope_methodology(self):
        methodology = MethodologyExtraction(
            heuristics=[
                Heuristic(trigger="When coding", procedure="Write tests first"),
                Heuristic(trigger="When analyzing data", procedure="Check distributions"),
            ],
        )
        teammate = AgentTeammate(
            name="Coder",
            archetype="Technical Builder",
            arch_key="technical_builder",
            description="Writes code",
            skills=[ExtractedSkill(
                name="Python coding",
                category=SkillCategory.HARD,
                context="Writing production code",
            )],
            personality={},
            benefit="",
        )

        forger = TeamForger()
        scoped = forger._scope_methodology(methodology, teammate)

        assert scoped is not None
        # Should include at least one heuristic
        assert len(scoped.heuristics) >= 1


class TestConductorGenerator:
    def _make_forged_teammates(self) -> list[ForgedTeammate]:
        skills_a = [ExtractedSkill(name="Python", category=SkillCategory.HARD, context="coding")]
        skills_b = [ExtractedSkill(name="Data Analysis", category=SkillCategory.DOMAIN, context="analytics")]

        tm_a = AgentTeammate(
            name="Code Architect", archetype="Technical Builder",
            arch_key="technical_builder", description="Builds code",
            skills=skills_a, personality={"rigor": 0.9}, benefit="Builds",
        )
        tm_b = AgentTeammate(
            name="Data Wrangler", archetype="Data Navigator",
            arch_key="data_navigator", description="Analyzes data",
            skills=skills_b, personality={"rigor": 0.8}, benefit="Analyzes",
        )

        return [
            ForgedTeammate(
                teammate=tm_a,
                identity_yaml="identity: a",
                skill_folder=SkillFolderResult(skill_name="code-architect", skill_md="# Code"),
            ),
            ForgedTeammate(
                teammate=tm_b,
                identity_yaml="identity: b",
                skill_folder=SkillFolderResult(skill_name="data-wrangler", skill_md="# Data"),
            ),
        ]

    def test_generate_conductor(self):
        extraction = _make_sample_extraction()
        forged = self._make_forged_teammates()
        team = AgentTeamComposition(
            role_title="Senior Data Engineer",
            teammates=[ft.teammate for ft in forged],
        )

        gen = ConductorGenerator()
        conductor = gen.generate(team, forged, extraction)

        assert conductor.skill_name
        assert "conductor" in conductor.skill_name
        assert "Team Conductor" in conductor.skill_md
        assert "Code Architect" in conductor.skill_md
        assert "Data Wrangler" in conductor.skill_md

    def test_routing_table(self):
        forged = self._make_forged_teammates()
        gen = ConductorGenerator()
        table = gen._build_routing_table(forged)

        assert "Code Architect" in table
        assert "Data Wrangler" in table
        assert len(table["Code Architect"]) > 0

    def test_handoffs(self):
        forged = self._make_forged_teammates()
        gen = ConductorGenerator()
        handoffs = gen._build_handoffs(forged)

        assert len(handoffs) >= 1
        assert handoffs[0].from_agent == "Code Architect"
        assert handoffs[0].to_agent == "Data Wrangler"


class TestOrchestrationConfig:
    def test_export_claude_code(self):
        conductor = ConductorSkill(
            skill_name="test-conductor",
            skill_md="# Conductor",
        )
        teammate = ForgedTeammate(
            teammate=AgentTeammate(
                name="Agent", archetype="Builder", arch_key="technical_builder",
                description="Builds", skills=[], personality={}, benefit="",
            ),
            identity_yaml="id: 1",
            skill_folder=SkillFolderResult(skill_name="builder", skill_md="# Builder"),
        )
        team = ForgedTeam(
            role_title="Engineer",
            conductor=conductor,
            teammates=[teammate],
        )

        exporter = OrchestrationConfigExporter()
        files = exporter.export_claude_code(team)

        assert ".claude/skills/test-conductor/SKILL.md" in files
        assert ".claude/skills/builder/SKILL.md" in files

    def test_export_orchestration_yaml(self):
        conductor = ConductorSkill(
            skill_name="test-conductor",
            skill_md="# Conductor",
            routing_table={"Agent": ["code", "build"]},
        )
        team = ForgedTeam(
            role_title="Engineer",
            conductor=conductor,
            teammates=[],
        )

        exporter = OrchestrationConfigExporter()
        yaml_str = exporter.export_orchestration_yaml(team)

        assert "Engineer" in yaml_str
        assert "test-conductor" in yaml_str


class TestModels:
    def test_handoff_protocol(self):
        hp = HandoffProtocol(
            from_agent="A", to_agent="B", trigger="When needed",
        )
        d = hp.to_dict()
        assert d["from_agent"] == "A"

    def test_workflow_step(self):
        step = WorkflowStep(agent="A", task="Do work", inputs=["context"], outputs=["result"])
        d = step.to_dict()
        assert d["agent"] == "A"

    def test_orchestrated_workflow(self):
        wf = OrchestratedWorkflow(
            name="Test Flow", trigger="When asked",
            steps=[WorkflowStep(agent="A", task="Work")],
        )
        d = wf.to_dict()
        assert len(d["steps"]) == 1

    def test_forged_team_to_dict(self):
        team = ForgedTeam(
            role_title="Engineer",
            conductor=ConductorSkill(skill_name="c", skill_md="# C"),
            teammates=[],
        )
        d = team.to_dict()
        assert d["role_title"] == "Engineer"


class TestTeamPipeline:
    def test_team_pipeline_stages(self):
        pipeline = ForgePipeline.team()
        names = [s.name for s in pipeline.stages]
        assert "team_compose" in names
        assert "team_forge" in names
        assert "conductor_generate" in names
        assert "analyze" in names
