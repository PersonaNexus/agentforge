"""Tests for Claude Code-compatible skill folder generation."""

from __future__ import annotations

import pytest

from agentforge.generation.identity_generator import IdentityGenerator
from agentforge.generation.skill_folder import SkillFolderGenerator, SkillFolderResult
from agentforge.models.extracted_skills import (
    ExtractionResult,
    ExtractedRole,
    ExtractedSkill,
    SkillCategory,
    SuggestedTraits,
)


@pytest.fixture
def sample_identity(sample_extraction):
    """Generate an identity from the sample extraction for testing."""
    gen = IdentityGenerator()
    identity, _ = gen.generate(sample_extraction)
    return identity


class TestSkillFolderResult:
    def test_result_has_required_fields(self, sample_extraction, sample_identity):
        generator = SkillFolderGenerator()
        result = generator.generate(sample_extraction, sample_identity)

        assert isinstance(result, SkillFolderResult)
        assert result.skill_name
        assert len(result.skill_md) > 0

    def test_skill_name_is_slug(self, sample_extraction, sample_identity):
        generator = SkillFolderGenerator()
        result = generator.generate(sample_extraction, sample_identity)

        assert result.skill_name == "senior-data-engineer"


class TestSkillMdFrontmatter:
    def test_has_yaml_frontmatter(self, sample_extraction, sample_identity):
        generator = SkillFolderGenerator()
        result = generator.generate(sample_extraction, sample_identity)

        assert result.skill_md.startswith("---\n")
        # Should have closing frontmatter delimiter
        parts = result.skill_md.split("---\n", 2)
        assert len(parts) >= 3  # empty before ---, frontmatter, body

    def test_frontmatter_has_name(self, sample_extraction, sample_identity):
        generator = SkillFolderGenerator()
        result = generator.generate(sample_extraction, sample_identity)

        assert "name: senior-data-engineer" in result.skill_md

    def test_frontmatter_has_description(self, sample_extraction, sample_identity):
        generator = SkillFolderGenerator()
        result = generator.generate(sample_extraction, sample_identity)

        assert "description: Design, build, and maintain scalable data" in result.skill_md

    def test_frontmatter_has_allowed_tools(self, sample_extraction, sample_identity):
        generator = SkillFolderGenerator()
        result = generator.generate(sample_extraction, sample_identity)

        assert "allowed-tools:" in result.skill_md


class TestSkillMdBody:
    def test_has_role_title(self, sample_extraction, sample_identity):
        generator = SkillFolderGenerator()
        result = generator.generate(sample_extraction, sample_identity)

        assert "# Senior Data Engineer" in result.skill_md

    def test_has_purpose(self, sample_extraction, sample_identity):
        generator = SkillFolderGenerator()
        result = generator.generate(sample_extraction, sample_identity)

        assert "Design, build, and maintain scalable data infrastructure" in result.skill_md

    def test_has_trigger_patterns(self, sample_extraction, sample_identity):
        generator = SkillFolderGenerator()
        result = generator.generate(sample_extraction, sample_identity)

        assert "## When to Use This Skill" in result.skill_md
        assert "Activate this skill" in result.skill_md
        assert "ETL pipeline design" in result.skill_md
        assert "Data warehouse architecture" in result.skill_md

    def test_triggers_include_responsibilities(self, sample_extraction, sample_identity):
        generator = SkillFolderGenerator()
        result = generator.generate(sample_extraction, sample_identity)

        assert "Design and implement scalable ETL/ELT pipelines" in result.skill_md

    def test_has_identity_and_personality(self, sample_extraction, sample_identity):
        generator = SkillFolderGenerator()
        result = generator.generate(sample_extraction, sample_identity)

        assert "## Identity & Personality" in result.skill_md
        assert "senior" in result.skill_md
        assert "Data Engineering" in result.skill_md

    def test_has_personality_modifiers(self, sample_extraction, sample_identity):
        generator = SkillFolderGenerator()
        result = generator.generate(sample_extraction, sample_identity)

        assert "Rigor" in result.skill_md
        assert "Directness" in result.skill_md
        assert "Patience" in result.skill_md
        assert "Creativity" in result.skill_md

    def test_personality_modifiers_include_prompts(self, sample_extraction, sample_identity):
        generator = SkillFolderGenerator()
        result = generator.generate(sample_extraction, sample_identity)

        assert "Apply rigorous methodology" in result.skill_md

    def test_has_communication_style(self, sample_extraction, sample_identity):
        generator = SkillFolderGenerator()
        result = generator.generate(sample_extraction, sample_identity)

        assert "### Communication Style" in result.skill_md
        assert "precise and straightforward" in result.skill_md

    def test_has_core_competencies(self, sample_extraction, sample_identity):
        generator = SkillFolderGenerator()
        result = generator.generate(sample_extraction, sample_identity)

        assert "## Core Competencies" in result.skill_md

    def test_has_domain_expertise(self, sample_extraction, sample_identity):
        generator = SkillFolderGenerator()
        result = generator.generate(sample_extraction, sample_identity)

        assert "### Domain Expertise" in result.skill_md
        assert "Data Architecture" in result.skill_md
        assert "AI-assisted schema evolution" in result.skill_md

    def test_has_technical_skills(self, sample_extraction, sample_identity):
        generator = SkillFolderGenerator()
        result = generator.generate(sample_extraction, sample_identity)

        assert "### Technical Skills" in result.skill_md
        assert "Python" in result.skill_md
        assert "SQL" in result.skill_md
        assert "pandas" in result.skill_md

    def test_has_tools_and_platforms(self, sample_extraction, sample_identity):
        generator = SkillFolderGenerator()
        result = generator.generate(sample_extraction, sample_identity)

        assert "### Tools & Platforms" in result.skill_md
        assert "Apache Spark" in result.skill_md
        assert "Spark SQL" in result.skill_md

    def test_has_workflows(self, sample_extraction, sample_identity):
        generator = SkillFolderGenerator()
        result = generator.generate(sample_extraction, sample_identity)

        assert "## Workflows" in result.skill_md
        assert "### Workflow 1:" in result.skill_md
        assert "### Workflow 2:" in result.skill_md

    def test_workflows_have_steps(self, sample_extraction, sample_identity):
        generator = SkillFolderGenerator()
        result = generator.generate(sample_extraction, sample_identity)

        assert "1. Clarify requirements" in result.skill_md
        assert "2. Assess the current state" in result.skill_md
        assert "Leverage relevant tools" in result.skill_md

    def test_has_scope_and_boundaries(self, sample_extraction, sample_identity):
        generator = SkillFolderGenerator()
        result = generator.generate(sample_extraction, sample_identity)

        assert "## Scope & Boundaries" in result.skill_md
        assert "### In Scope" in result.skill_md
        assert "ETL pipeline design" in result.skill_md

    def test_has_secondary_scope(self, sample_extraction, sample_identity):
        generator = SkillFolderGenerator()
        result = generator.generate(sample_extraction, sample_identity)

        assert "### Secondary (Defer When Possible)" in result.skill_md
        assert "ML model operationalization" in result.skill_md

    def test_has_guardrails(self, sample_extraction, sample_identity):
        generator = SkillFolderGenerator()
        result = generator.generate(sample_extraction, sample_identity)

        assert "### Guardrails" in result.skill_md
        assert "Data Engineering" in result.skill_md
        assert "team collaboration" in result.skill_md

    def test_has_audience(self, sample_extraction, sample_identity):
        generator = SkillFolderGenerator()
        result = generator.generate(sample_extraction, sample_identity)

        assert "## Audience" in result.skill_md
        assert "Data scientists" in result.skill_md
        assert "Analysts" in result.skill_md

    def test_has_footer(self, sample_extraction, sample_identity):
        generator = SkillFolderGenerator()
        result = generator.generate(sample_extraction, sample_identity)

        assert "Generated by AgentForge" in result.skill_md

    def test_footer_with_jd(self, sample_extraction, sample_identity, sample_jd):
        generator = SkillFolderGenerator()
        result = generator.generate(sample_extraction, sample_identity, jd=sample_jd)

        assert "Senior Data Engineer at Acme Technologies" in result.skill_md


class TestMinimalExtraction:
    def test_minimal_produces_valid_output(self):
        extraction = ExtractionResult(
            role=ExtractedRole(
                title="Test Agent",
                purpose="A test agent for validation",
                domain="general",
            ),
        )
        gen = IdentityGenerator()
        identity, _ = gen.generate(extraction)

        generator = SkillFolderGenerator()
        result = generator.generate(extraction, identity)

        assert result.skill_name == "test-agent"
        assert "# Test Agent" in result.skill_md
        assert result.skill_md.startswith("---\n")
        assert "name: test-agent" in result.skill_md

    def test_no_traits_still_works(self):
        extraction = ExtractionResult(
            role=ExtractedRole(
                title="Bot",
                purpose="Do stuff",
                domain="general",
            ),
            suggested_traits=SuggestedTraits(),  # all None
        )
        gen = IdentityGenerator()
        identity, _ = gen.generate(extraction)

        generator = SkillFolderGenerator()
        result = generator.generate(extraction, identity)

        assert "## Identity & Personality" in result.skill_md
        # No personality modifiers when no traits defined
        assert "### Personality Modifiers" not in result.skill_md

    def test_no_responsibilities_skips_workflows(self):
        extraction = ExtractionResult(
            role=ExtractedRole(
                title="Clerk",
                purpose="Process documents",
                domain="admin",
            ),
        )
        gen = IdentityGenerator()
        identity, _ = gen.generate(extraction)

        generator = SkillFolderGenerator()
        result = generator.generate(extraction, identity)

        assert "## Workflows" not in result.skill_md

    def test_no_tools_skips_mcp(self):
        extraction = ExtractionResult(
            role=ExtractedRole(
                title="Writer",
                purpose="Write content",
                domain="content",
            ),
            skills=[
                ExtractedSkill(
                    name="Writing",
                    category=SkillCategory.SOFT,
                    context="Content creation",
                ),
            ],
        )
        gen = IdentityGenerator()
        identity, _ = gen.generate(extraction)

        generator = SkillFolderGenerator()
        result = generator.generate(extraction, identity)

        # No MCP section when no tool/hard skills with genai_application
        assert "## MCP Tool Integration" not in result.skill_md
