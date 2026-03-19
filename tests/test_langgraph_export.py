"""Tests for LangGraph export functionality."""
from __future__ import annotations

import ast

import pytest

from agentforge.analysis.team_composer import AgentTeamComposition, AgentTeammate
from agentforge.composition.conductor_generator import ConductorGenerator
from agentforge.composition.langgraph_export import LangGraphExporter, _to_python_id
from agentforge.composition.models import (
    ConductorSkill,
    ForgedTeam,
    ForgedTeammate,
    HandoffProtocol,
    OrchestratedWorkflow,
    WorkflowStep,
)
from agentforge.composition.orchestration_config import OrchestrationConfigExporter
from agentforge.generation.skill_folder import SkillFolderResult
from agentforge.models.extracted_skills import ExtractedSkill, SkillCategory

from tests.conftest import _make_sample_extraction


def _make_forged_team() -> ForgedTeam:
    """Create a sample ForgedTeam for testing."""
    skills_a = [ExtractedSkill(name="Python", category=SkillCategory.HARD, context="coding")]
    skills_b = [
        ExtractedSkill(name="Data Analysis", category=SkillCategory.DOMAIN, context="analytics")
    ]

    tm_a = AgentTeammate(
        name="Code Architect",
        archetype="Technical Builder",
        arch_key="technical_builder",
        description="Builds code",
        skills=skills_a,
        personality={"rigor": 0.9},
        benefit="Builds",
    )
    tm_b = AgentTeammate(
        name="Data Wrangler",
        archetype="Data Navigator",
        arch_key="data_navigator",
        description="Analyzes data",
        skills=skills_b,
        personality={"rigor": 0.8},
        benefit="Analyzes",
    )

    teammates = [
        ForgedTeammate(
            teammate=tm_a,
            identity_yaml="identity: a",
            skill_folder=SkillFolderResult(skill_name="code-architect", skill_md="# Code Architect"),
        ),
        ForgedTeammate(
            teammate=tm_b,
            identity_yaml="identity: b",
            skill_folder=SkillFolderResult(skill_name="data-wrangler", skill_md="# Data Wrangler"),
        ),
    ]

    conductor = ConductorSkill(
        skill_name="test-conductor",
        skill_md="# Conductor",
        routing_table={
            "Code Architect": ["python", "code", "build", "test"],
            "Data Wrangler": ["data", "analysis", "query", "pipeline"],
        },
        workflows=[
            OrchestratedWorkflow(
                name="Data Pipeline Build",
                trigger="Build a new data pipeline",
                steps=[
                    WorkflowStep(
                        agent="Data Wrangler",
                        task="Analyze data requirements",
                        inputs=["initial context"],
                        outputs=["data spec"],
                    ),
                    WorkflowStep(
                        agent="Code Architect",
                        task="Implement pipeline code",
                        inputs=["data spec"],
                        outputs=["pipeline code"],
                    ),
                ],
            ),
        ],
        handoffs=[
            HandoffProtocol(
                from_agent="Code Architect",
                to_agent="Data Wrangler",
                trigger="When code produces output needing data review",
            ),
        ],
    )

    return ForgedTeam(
        role_title="Senior Data Engineer",
        conductor=conductor,
        teammates=teammates,
    )


class TestToPythonId:
    def test_simple_name(self):
        assert _to_python_id("Code Architect") == "code_architect"

    def test_special_characters(self):
        assert _to_python_id("Data-Wrangler (v2)") == "data_wrangler_v2"

    def test_leading_digit(self):
        assert _to_python_id("3D Modeler") == "agent_3d_modeler"

    def test_empty_string(self):
        assert _to_python_id("") == "agent"


class TestLangGraphExporter:
    def test_export_produces_valid_python(self):
        team = _make_forged_team()
        exporter = LangGraphExporter()
        code = exporter.export(team)

        # Should parse as valid Python
        ast.parse(code)

    def test_export_contains_state_class(self):
        team = _make_forged_team()
        code = LangGraphExporter().export(team)

        assert "class TeamState" in code
        assert "TypedDict" in code

    def test_export_contains_agent_nodes(self):
        team = _make_forged_team()
        code = LangGraphExporter().export(team)

        assert "code_architect" in code
        assert "data_wrangler" in code
        assert "AGENT_SKILLS" in code

    def test_export_contains_routing(self):
        team = _make_forged_team()
        code = LangGraphExporter().export(team)

        assert "ROUTING_TABLE" in code
        assert "route_task" in code
        assert "python" in code  # routing keyword

    def test_export_contains_graph_construction(self):
        team = _make_forged_team()
        code = LangGraphExporter().export(team)

        assert "def build_graph" in code
        assert "StateGraph" in code
        assert "set_conditional_entry_point" in code
        assert "graph.compile()" in code

    def test_export_contains_workflows(self):
        team = _make_forged_team()
        code = LangGraphExporter().export(team)

        assert "WORKFLOWS" in code
        assert "Data Pipeline Build" in code

    def test_export_contains_main(self):
        team = _make_forged_team()
        code = LangGraphExporter().export(team)

        assert 'if __name__ == "__main__"' in code
        assert "app.invoke" in code

    def test_export_contains_imports(self):
        team = _make_forged_team()
        code = LangGraphExporter().export(team)

        assert "from langgraph.graph import" in code
        assert "from langchain_core.messages import" in code

    def test_export_no_workflows(self):
        """Test export when team has no workflows."""
        team = _make_forged_team()
        team.conductor.workflows = []
        code = LangGraphExporter().export(team)

        # Should still be valid Python
        ast.parse(code)
        assert "No multi-agent workflows" in code

    def test_export_with_full_conductor(self):
        """Test export using ConductorGenerator output."""
        extraction = _make_sample_extraction()
        team = _make_forged_team()

        # Use the real conductor generator
        gen = ConductorGenerator()
        team_comp = AgentTeamComposition(
            role_title="Senior Data Engineer",
            teammates=[ft.teammate for ft in team.teammates],
        )
        conductor = gen.generate(team_comp, team.teammates, extraction)
        team.conductor = conductor

        code = LangGraphExporter().export(team)
        ast.parse(code)
        assert "code_architect" in code
        assert "data_wrangler" in code


class TestOrchestrationConfigLangGraph:
    def test_export_langgraph_via_config_exporter(self):
        team = _make_forged_team()
        exporter = OrchestrationConfigExporter()
        code = exporter.export_langgraph(team)

        ast.parse(code)
        assert "TeamState" in code
        assert "build_graph" in code
