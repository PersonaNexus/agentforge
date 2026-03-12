"""Tests for ClawHub-compatible skill generation."""

from __future__ import annotations

import pytest

from agentforge.generation.clawhub_skill import ClawHubSkillGenerator, ClawHubSkillResult
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


@pytest.fixture
def sample_methodology():
    return MethodologyExtraction(
        heuristics=[
            Heuristic(
                trigger="New data source integration request",
                procedure="1. Profile the source schema\n2. Assess volume and velocity\n3. Choose batch vs streaming",
            ),
        ],
        output_templates=[
            OutputTemplate(
                name="Pipeline Design Doc",
                when_to_use="Starting a new ETL pipeline",
                template="## Pipeline: {name}\n\n**Source:** {source}\n**Sink:** {sink}\n**SLA:** {sla}",
            ),
        ],
        trigger_mappings=[
            TriggerTechniqueMapping(
                trigger_pattern="data quality issue",
                technique="Root cause analysis with lineage tracing",
                output_format="Incident report",
            ),
        ],
        quality_criteria=[
            QualityCriterion(
                criterion="Pipeline idempotency",
                description="Re-running should not create duplicates",
            ),
        ],
    )


class TestClawHubSkillResult:
    def test_result_has_required_fields(self, sample_extraction):
        gen = ClawHubSkillGenerator()
        result = gen.generate(sample_extraction)

        assert isinstance(result, ClawHubSkillResult)
        assert result.skill_name
        assert len(result.skill_md) > 0

    def test_skill_name_is_clawhub_slug(self, sample_extraction):
        gen = ClawHubSkillGenerator()
        result = gen.generate(sample_extraction)

        assert result.skill_name == "senior-data-engineer"
        # Must match ^[a-z0-9][a-z0-9-]*$
        assert result.skill_name[0].isalnum()
        assert all(c.isalnum() or c == "-" for c in result.skill_name)


class TestClawHubFrontmatter:
    def test_has_yaml_frontmatter(self, sample_extraction):
        gen = ClawHubSkillGenerator()
        result = gen.generate(sample_extraction)

        assert result.skill_md.startswith("---\n")
        parts = result.skill_md.split("---\n", 2)
        assert len(parts) >= 3

    def test_frontmatter_has_name(self, sample_extraction):
        gen = ClawHubSkillGenerator()
        result = gen.generate(sample_extraction)

        assert "name: senior-data-engineer" in result.skill_md

    def test_frontmatter_has_description(self, sample_extraction):
        gen = ClawHubSkillGenerator()
        result = gen.generate(sample_extraction)

        assert 'description: "' in result.skill_md

    def test_frontmatter_has_version(self, sample_extraction):
        gen = ClawHubSkillGenerator()
        result = gen.generate(sample_extraction)

        assert "version: 1.0.0" in result.skill_md

    def test_frontmatter_infers_bins(self, sample_extraction):
        gen = ClawHubSkillGenerator()
        result = gen.generate(sample_extraction)

        # sample_extraction has Python (hard) -> python3
        assert "python3" in result.skill_md

    def test_long_description_truncated(self):
        extraction = ExtractionResult(
            role=ExtractedRole(
                title="Agent",
                purpose="A" * 250,
                domain="test",
            ),
        )
        gen = ClawHubSkillGenerator()
        result = gen.generate(extraction)

        # Frontmatter description should be truncated to 200 chars
        frontmatter = result.skill_md.split("---\n")[1]
        desc_line = [l for l in frontmatter.split("\n") if l.startswith("description:")][0]
        # The quoted description content (minus key and quotes) should be <= 200
        desc_content = desc_line.split('"')[1]
        assert len(desc_content) <= 200
        assert desc_content.endswith("...")


class TestClawHubBody:
    def test_has_role_title(self, sample_extraction):
        gen = ClawHubSkillGenerator()
        result = gen.generate(sample_extraction)

        assert "# Senior Data Engineer" in result.skill_md

    def test_has_purpose(self, sample_extraction):
        gen = ClawHubSkillGenerator()
        result = gen.generate(sample_extraction)

        assert "Design, build, and maintain scalable data infrastructure" in result.skill_md

    def test_no_persona_layer(self, sample_extraction):
        gen = ClawHubSkillGenerator()
        result = gen.generate(sample_extraction)

        # ClawHub should NOT have identity/persona sections
        assert "## Identity" not in result.skill_md
        assert "Personality" not in result.skill_md

    def test_has_workflows_without_methodology(self, sample_extraction):
        gen = ClawHubSkillGenerator()
        result = gen.generate(sample_extraction)

        assert "## Workflows" in result.skill_md
        assert "Design and implement scalable ETL/ELT pipelines" in result.skill_md

    def test_has_skills_section(self, sample_extraction):
        gen = ClawHubSkillGenerator()
        result = gen.generate(sample_extraction)

        assert "## Skills" in result.skill_md
        assert "**Python**" in result.skill_md
        assert "**Data Architecture**" in result.skill_md

    def test_excludes_soft_skills(self, sample_extraction):
        gen = ClawHubSkillGenerator()
        result = gen.generate(sample_extraction)

        # Soft skills should be excluded from compact listing
        assert "**Team Collaboration**" not in result.skill_md

    def test_has_scope(self, sample_extraction):
        gen = ClawHubSkillGenerator()
        result = gen.generate(sample_extraction)

        assert "## Scope" in result.skill_md
        assert "ETL pipeline design" in result.skill_md

    def test_has_secondary_scope(self, sample_extraction):
        gen = ClawHubSkillGenerator()
        result = gen.generate(sample_extraction)

        assert "Secondary (defer when possible):" in result.skill_md
        assert "ML model operationalization" in result.skill_md

    def test_has_footer(self, sample_extraction):
        gen = ClawHubSkillGenerator()
        result = gen.generate(sample_extraction)

        assert "Generated by AgentForge" in result.skill_md

    def test_footer_with_jd(self, sample_extraction, sample_jd):
        gen = ClawHubSkillGenerator()
        result = gen.generate(sample_extraction, jd=sample_jd)

        assert "Senior Data Engineer at Acme Technologies" in result.skill_md


class TestClawHubMethodology:
    def test_routing_section(self, sample_extraction, sample_methodology):
        gen = ClawHubSkillGenerator()
        result = gen.generate(sample_extraction, methodology=sample_methodology)

        assert "## Routing" in result.skill_md
        assert "data quality issue" in result.skill_md
        assert "Root cause analysis" in result.skill_md

    def test_decision_rules(self, sample_extraction, sample_methodology):
        gen = ClawHubSkillGenerator()
        result = gen.generate(sample_extraction, methodology=sample_methodology)

        assert "## Decision Rules" in result.skill_md
        assert "New data source integration request" in result.skill_md
        assert "Profile the source schema" in result.skill_md

    def test_templates(self, sample_extraction, sample_methodology):
        gen = ClawHubSkillGenerator()
        result = gen.generate(sample_extraction, methodology=sample_methodology)

        assert "## Templates" in result.skill_md
        assert "Pipeline Design Doc" in result.skill_md
        assert "Starting a new ETL pipeline" in result.skill_md

    def test_quality_bar_checkboxes(self, sample_extraction, sample_methodology):
        gen = ClawHubSkillGenerator()
        result = gen.generate(sample_extraction, methodology=sample_methodology)

        assert "## Quality Bar" in result.skill_md
        assert "- [ ] Pipeline idempotency" in result.skill_md
        assert "Re-running should not create duplicates" in result.skill_md

    def test_no_workflows_when_methodology_present(self, sample_extraction, sample_methodology):
        gen = ClawHubSkillGenerator()
        result = gen.generate(sample_extraction, methodology=sample_methodology)

        # When methodology is present, Workflows section should be replaced by methodology sections
        assert "## Workflows" not in result.skill_md


class TestClawHubMinimal:
    def test_minimal_extraction(self):
        extraction = ExtractionResult(
            role=ExtractedRole(
                title="Test Bot",
                purpose="Do testing",
                domain="qa",
            ),
        )
        gen = ClawHubSkillGenerator()
        result = gen.generate(extraction)

        assert result.skill_name == "test-bot"
        assert "# Test Bot" in result.skill_md
        assert result.skill_md.startswith("---\n")
        assert "version: 1.0.0" in result.skill_md

    def test_no_bins_no_envs(self):
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
        gen = ClawHubSkillGenerator()
        result = gen.generate(extraction)

        # No metadata.openclaw block when no bins or env vars
        assert "openclaw:" not in result.skill_md

    def test_slug_max_length(self):
        extraction = ExtractionResult(
            role=ExtractedRole(
                title="A" * 100 + " Engineer",
                purpose="Test",
                domain="test",
            ),
        )
        gen = ClawHubSkillGenerator()
        result = gen.generate(extraction)

        assert len(result.skill_name) <= 64

    def test_slug_no_leading_special_chars(self):
        extraction = ExtractionResult(
            role=ExtractedRole(
                title="---Special Agent",
                purpose="Test",
                domain="test",
            ),
        )
        gen = ClawHubSkillGenerator()
        result = gen.generate(extraction)

        assert result.skill_name[0].isalnum()


class TestClawHubEnvInference:
    def test_aws_env_var(self):
        extraction = ExtractionResult(
            role=ExtractedRole(title="Cloud Engineer", purpose="Cloud stuff", domain="cloud"),
            skills=[
                ExtractedSkill(name="AWS", category=SkillCategory.TOOL, context="Cloud provider"),
            ],
        )
        gen = ClawHubSkillGenerator()
        result = gen.generate(extraction)

        assert "AWS_ACCESS_KEY_ID" in result.skill_md
        assert "primaryEnv: AWS_ACCESS_KEY_ID" in result.skill_md

    def test_github_env_var(self):
        extraction = ExtractionResult(
            role=ExtractedRole(title="DevOps", purpose="CI/CD", domain="devops"),
            skills=[
                ExtractedSkill(name="GitHub", category=SkillCategory.TOOL, context="Source control"),
            ],
        )
        gen = ClawHubSkillGenerator()
        result = gen.generate(extraction)

        assert "GITHUB_TOKEN" in result.skill_md
