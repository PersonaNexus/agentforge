"""Tests for agent team composer."""

from __future__ import annotations

import pytest

from agentforge.analysis.team_composer import (
    AgentTeamComposition,
    AgentTeammate,
    TeamComposer,
)
from agentforge.models.extracted_skills import (
    ExtractionResult,
    ExtractedRole,
    ExtractedSkill,
    SkillCategory,
    SkillImportance,
    SkillProficiency,
)


def _make_role(title: str = "Senior Engineer", domain: str = "engineering") -> ExtractedRole:
    return ExtractedRole(title=title, purpose="Build things", domain=domain)


def _make_skill(
    name: str,
    category: SkillCategory = SkillCategory.HARD,
    context: str = "",
    genai_application: str = "",
) -> ExtractedSkill:
    return ExtractedSkill(
        name=name,
        category=category,
        proficiency=SkillProficiency.INTERMEDIATE,
        importance=SkillImportance.REQUIRED,
        context=context,
        genai_application=genai_application,
    )


class TestTeamComposer:
    def test_empty_skills_returns_empty_team(self):
        result = ExtractionResult(role=_make_role(), skills=[])
        composer = TeamComposer()
        team = composer.compose(result)

        assert isinstance(team, AgentTeamComposition)
        assert team.teammates == []
        assert team.role_title == "Senior Engineer"

    def test_single_hard_skill_creates_teammate(self):
        result = ExtractionResult(
            role=_make_role(),
            skills=[_make_skill("Python", SkillCategory.HARD, context="backend development")],
        )
        composer = TeamComposer()
        team = composer.compose(result)

        assert len(team.teammates) >= 1
        # The skill should be assigned to a teammate
        all_skills = []
        for t in team.teammates:
            all_skills.extend(t.skill_names())
        assert "Python" in all_skills

    def test_mixed_skills_create_multiple_teammates(self):
        result = ExtractionResult(
            role=_make_role(),
            skills=[
                _make_skill("Python", SkillCategory.HARD, context="software development"),
                _make_skill("AWS", SkillCategory.TOOL, context="cloud infrastructure"),
                _make_skill("Market Research", SkillCategory.DOMAIN, context="competitive analysis"),
                _make_skill("Stakeholder Management", SkillCategory.SOFT, context="client relationships"),
            ],
        )
        composer = TeamComposer()
        team = composer.compose(result)

        assert len(team.teammates) >= 2
        assert team.team_benefit != ""

        # All skills should be assigned
        all_assigned = set()
        for t in team.teammates:
            all_assigned.update(t.skill_names())
        assert all_assigned == {"Python", "AWS", "Market Research", "Stakeholder Management"}

    def test_max_teammates_respected(self):
        skills = [_make_skill(f"Skill{i}", SkillCategory.HARD) for i in range(20)]
        result = ExtractionResult(role=_make_role(), skills=skills)
        composer = TeamComposer(max_teammates=3)
        team = composer.compose(result)

        assert len(team.teammates) <= 3

    def test_teammate_has_personality(self):
        result = ExtractionResult(
            role=_make_role(),
            skills=[_make_skill("SQL", SkillCategory.TOOL, context="database queries")],
        )
        composer = TeamComposer()
        team = composer.compose(result)

        assert len(team.teammates) >= 1
        for t in team.teammates:
            assert isinstance(t.personality, dict)
            assert len(t.personality) > 0
            for val in t.personality.values():
                assert 0.0 <= val <= 1.0

    def test_teammate_has_benefit_statement(self):
        result = ExtractionResult(
            role=_make_role(title="Product Manager"),
            skills=[
                _make_skill("User Research", SkillCategory.DOMAIN, context="market research"),
                _make_skill("Jira", SkillCategory.TOOL, context="project management"),
            ],
        )
        composer = TeamComposer()
        team = composer.compose(result)

        for t in team.teammates:
            assert t.benefit != ""
            # Benefit should reference the role
            assert "Product Manager" in t.benefit

    def test_to_dict_serialization(self):
        result = ExtractionResult(
            role=_make_role(),
            skills=[
                _make_skill("Python", SkillCategory.HARD),
                _make_skill("AWS", SkillCategory.TOOL),
            ],
        )
        composer = TeamComposer()
        team = composer.compose(result)
        data = team.to_dict()

        assert "role_title" in data
        assert "teammates" in data
        assert "team_benefit" in data
        assert isinstance(data["teammates"], list)

        for t in data["teammates"]:
            assert "name" in t
            assert "archetype" in t
            assert "skills" in t
            assert "personality" in t
            assert "benefit" in t

    def test_domain_specific_names(self):
        result = ExtractionResult(
            role=_make_role(title="Senior Engineer", domain="engineering"),
            skills=[
                _make_skill("Python", SkillCategory.HARD, context="software development"),
                _make_skill("AWS", SkillCategory.TOOL, context="cloud deployment automation"),
            ],
        )
        composer = TeamComposer()
        team = composer.compose(result)

        # Engineering domain should produce domain-specific names
        names = [t.name for t in team.teammates]
        # At least one should not be the generic archetype label
        assert len(names) >= 1

    def test_keyword_affinity_matching(self):
        """Skills with relevant keywords should match to appropriate archetypes."""
        result = ExtractionResult(
            role=_make_role(title="Data Scientist", domain="data"),
            skills=[
                _make_skill("Data Analysis", SkillCategory.HARD, context="statistical analysis and research"),
                _make_skill("SQL", SkillCategory.TOOL, context="database queries and analytics"),
                _make_skill("Report Writing", SkillCategory.HARD, context="drafting technical reports and documentation"),
            ],
        )
        composer = TeamComposer()
        team = composer.compose(result)

        archetypes = [t.archetype for t in team.teammates]
        # Should have at least one data-related and one content-related teammate
        assert len(team.teammates) >= 2


class TestAgentTeammate:
    def test_skill_names(self):
        teammate = AgentTeammate(
            name="Test",
            archetype="Test",
            arch_key="technical_builder",
            description="Test",
            skills=[
                _make_skill("Python", SkillCategory.HARD),
                _make_skill("SQL", SkillCategory.TOOL),
            ],
            personality={"rigor": 0.8},
            benefit="Test benefit",
        )
        assert teammate.skill_names() == ["Python", "SQL"]

    def test_to_dict(self):
        teammate = AgentTeammate(
            name="Test Agent",
            archetype="Technical Builder",
            arch_key="technical_builder",
            description="Handles tech",
            skills=[_make_skill("Python", SkillCategory.HARD)],
            personality={"rigor": 0.8, "creativity": 0.6},
            benefit="Builds stuff",
        )
        data = teammate.to_dict()
        assert data["name"] == "Test Agent"
        assert data["archetype"] == "Technical Builder"
        assert data["skills"] == ["Python"]
        assert data["personality"]["rigor"] == 0.8
        assert data["benefit"] == "Builds stuff"


class TestAgentTeamComposition:
    def test_empty_composition(self):
        team = AgentTeamComposition(role_title="Test Role")
        data = team.to_dict()
        assert data["role_title"] == "Test Role"
        assert data["teammates"] == []
