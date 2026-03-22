"""Tests for Claude Code-compatible skill folder generation."""

from __future__ import annotations

import pytest

from agentforge.generation.identity_generator import IdentityGenerator
from agentforge.generation.skill_folder import SkillFolderGenerator, SkillFolderResult
from agentforge.models.extracted_skills import (
    ExtractionResult,
    ExtractedRole,
    ExtractedSkill,
    Heuristic,
    MethodologyExtraction,
    OutputTemplate,
    QualityCriterion,
    SkillCategory,
    SuggestedTraits,
    TriggerTechniqueMapping,
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

    def test_generates_supplementary_files(self, sample_extraction, sample_identity):
        generator = SkillFolderGenerator()
        result = generator.generate(sample_extraction, sample_identity)

        assert "instructions/voice.md" in result.supplementary_files
        assert "instructions/methodology.md" in result.supplementary_files
        assert "instructions/scope.md" in result.supplementary_files
        assert "eval/checklist.md" in result.supplementary_files
        assert "eval/advisory-board.md" in result.supplementary_files
        assert "examples/bad/anti-patterns.md" in result.supplementary_files


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

        assert "description:" in result.skill_md
        assert "Design, build, and maintain scalable data" in result.skill_md

    def test_frontmatter_has_allowed_tools(self, sample_extraction, sample_identity):
        generator = SkillFolderGenerator()
        result = generator.generate(sample_extraction, sample_identity)

        assert "allowed-tools:" in result.skill_md


class TestSkillMdOrchestrator:
    """Test that SKILL.md is a thin orchestrator routing to supplementary files."""

    def test_has_role_title(self, sample_extraction, sample_identity):
        generator = SkillFolderGenerator()
        result = generator.generate(sample_extraction, sample_identity)

        assert "# Senior Data Engineer" in result.skill_md

    def test_has_purpose(self, sample_extraction, sample_identity):
        generator = SkillFolderGenerator()
        result = generator.generate(sample_extraction, sample_identity)

        assert "Design, build, and maintain scalable data infrastructure" in result.skill_md

    def test_has_identity_and_personality(self, sample_extraction, sample_identity):
        generator = SkillFolderGenerator()
        result = generator.generate(sample_extraction, sample_identity)

        assert "## Identity" in result.skill_md
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

        assert "Communication style" in result.skill_md
        assert "precise and straightforward" in result.skill_md

    def test_routes_to_instructions(self, sample_extraction, sample_identity):
        generator = SkillFolderGenerator()
        result = generator.generate(sample_extraction, sample_identity)

        assert "## Instructions" in result.skill_md
        assert "`instructions/voice.md`" in result.skill_md
        assert "`instructions/methodology.md`" in result.skill_md
        assert "`instructions/scope.md`" in result.skill_md

    def test_routes_to_eval(self, sample_extraction, sample_identity):
        generator = SkillFolderGenerator()
        result = generator.generate(sample_extraction, sample_identity)

        assert "## Evaluation" in result.skill_md
        assert "`eval/checklist.md`" in result.skill_md
        assert "`eval/advisory-board.md`" in result.skill_md

    def test_routes_to_examples(self, sample_extraction, sample_identity):
        generator = SkillFolderGenerator()
        result = generator.generate(sample_extraction, sample_identity)

        assert "## Examples" in result.skill_md
        assert "`examples/good/`" in result.skill_md
        assert "`examples/bad/`" in result.skill_md

    def test_has_footer(self, sample_extraction, sample_identity):
        generator = SkillFolderGenerator()
        result = generator.generate(sample_extraction, sample_identity)

        assert "Generated by AgentForge" in result.skill_md

    def test_footer_with_jd(self, sample_extraction, sample_identity, sample_jd):
        generator = SkillFolderGenerator()
        result = generator.generate(sample_extraction, sample_identity, jd=sample_jd)

        assert "Senior Data Engineer at Acme Technologies" in result.skill_md

    def test_does_not_inline_methodology(self, sample_extraction, sample_identity):
        """Detailed methodology content should be in supplementary files, not SKILL.md."""
        generator = SkillFolderGenerator()
        result = generator.generate(sample_extraction, sample_identity)

        # These sections now live in supplementary files
        assert "## Core Competencies" not in result.skill_md
        assert "## Scope & Boundaries" not in result.skill_md
        assert "## Audience" not in result.skill_md
        assert "## Workflows" not in result.skill_md


class TestVoiceFile:
    def test_voice_has_traits(self, sample_extraction, sample_identity):
        generator = SkillFolderGenerator()
        result = generator.generate(sample_extraction, sample_identity)
        voice = result.supplementary_files["instructions/voice.md"]

        assert "Rigor" in voice
        assert "Directness" in voice
        assert "Apply rigorous methodology" in voice

    def test_voice_has_communication_style(self, sample_extraction, sample_identity):
        generator = SkillFolderGenerator()
        result = generator.generate(sample_extraction, sample_identity)
        voice = result.supplementary_files["instructions/voice.md"]

        assert "## Communication Style" in voice
        assert "precise and straightforward" in voice

    def test_voice_no_traits(self):
        extraction = ExtractionResult(
            role=ExtractedRole(title="Bot", purpose="Do stuff", domain="general"),
            suggested_traits=SuggestedTraits(),
        )
        gen = IdentityGenerator()
        identity, _ = gen.generate(extraction)
        result = SkillFolderGenerator().generate(extraction, identity)
        voice = result.supplementary_files["instructions/voice.md"]

        assert "balanced, professional tone" in voice


class TestMethodologyFile:
    def test_fallback_has_triggers_and_workflows(self, sample_extraction, sample_identity):
        """Without methodology, methodology.md should have trigger patterns and workflows."""
        generator = SkillFolderGenerator()
        result = generator.generate(sample_extraction, sample_identity)
        meth = result.supplementary_files["instructions/methodology.md"]

        assert "## When to Use This Skill" in meth
        assert "ETL pipeline design" in meth
        assert "Data warehouse architecture" in meth
        assert "Design and implement scalable ETL/ELT pipelines" in meth
        assert "## Workflows" in meth
        assert "### Workflow 1:" in meth

    def test_with_methodology_has_frameworks(self, sample_extraction, sample_identity):
        methodology = MethodologyExtraction(
            heuristics=[Heuristic(trigger="When evaluating data", procedure="Step 1...")],
            trigger_mappings=[TriggerTechniqueMapping(trigger_pattern="analyze", technique="deep-dive")],
        )
        generator = SkillFolderGenerator()
        result = generator.generate(sample_extraction, sample_identity, methodology=methodology)
        meth = result.supplementary_files["instructions/methodology.md"]

        assert "## Decision Frameworks" in meth
        assert "When evaluating data" in meth
        assert "## Trigger → Technique Router" in meth
        assert "analyze" in meth


class TestScopeFile:
    def test_scope_has_competencies(self, sample_extraction, sample_identity):
        generator = SkillFolderGenerator()
        result = generator.generate(sample_extraction, sample_identity)
        scope = result.supplementary_files["instructions/scope.md"]

        assert "## Core Competencies" in scope
        assert "### Domain Expertise" in scope
        assert "Data Architecture" in scope
        assert "AI-assisted schema evolution" in scope

    def test_scope_has_technical_skills(self, sample_extraction, sample_identity):
        generator = SkillFolderGenerator()
        result = generator.generate(sample_extraction, sample_identity)
        scope = result.supplementary_files["instructions/scope.md"]

        assert "### Technical Skills" in scope
        assert "Python" in scope
        assert "SQL" in scope
        assert "pandas" in scope

    def test_scope_has_tools(self, sample_extraction, sample_identity):
        generator = SkillFolderGenerator()
        result = generator.generate(sample_extraction, sample_identity)
        scope = result.supplementary_files["instructions/scope.md"]

        assert "### Tools & Platforms" in scope
        assert "Apache Spark" in scope
        assert "Spark SQL" in scope

    def test_scope_has_boundaries(self, sample_extraction, sample_identity):
        generator = SkillFolderGenerator()
        result = generator.generate(sample_extraction, sample_identity)
        scope = result.supplementary_files["instructions/scope.md"]

        assert "## Scope & Boundaries" in scope
        assert "### In Scope" in scope
        assert "ETL pipeline design" in scope
        assert "### Secondary (Defer When Possible)" in scope
        assert "ML model operationalization" in scope

    def test_scope_has_guardrails(self, sample_extraction, sample_identity):
        generator = SkillFolderGenerator()
        result = generator.generate(sample_extraction, sample_identity)
        scope = result.supplementary_files["instructions/scope.md"]

        assert "### Guardrails" in scope
        assert "Data Engineering" in scope
        assert "team collaboration" in scope

    def test_scope_has_audience(self, sample_extraction, sample_identity):
        generator = SkillFolderGenerator()
        result = generator.generate(sample_extraction, sample_identity)
        scope = result.supplementary_files["instructions/scope.md"]

        assert "## Audience" in scope
        assert "Data scientists" in scope
        assert "Analysts" in scope


class TestEvalFiles:
    def test_checklist_has_criteria(self, sample_extraction, sample_identity):
        generator = SkillFolderGenerator()
        result = generator.generate(sample_extraction, sample_identity)
        checklist = result.supplementary_files["eval/checklist.md"]

        assert "# Quality Checklist" in checklist
        assert "- [ ]" in checklist

    def test_checklist_with_methodology_criteria(self, sample_extraction, sample_identity):
        methodology = MethodologyExtraction(
            quality_criteria=[
                QualityCriterion(criterion="Data-backed claims", description="All claims need evidence"),
            ],
        )
        generator = SkillFolderGenerator()
        result = generator.generate(sample_extraction, sample_identity, methodology=methodology)
        checklist = result.supplementary_files["eval/checklist.md"]

        assert "Data-backed claims" in checklist
        assert "All claims need evidence" in checklist

    def test_advisory_board_has_reviewers(self, sample_extraction, sample_identity):
        generator = SkillFolderGenerator()
        result = generator.generate(sample_extraction, sample_identity)
        board = result.supplementary_files["eval/advisory-board.md"]

        assert "# Advisory Board" in board
        assert "## The Domain Expert" in board
        assert "## The End User" in board
        assert "## The Skeptic" in board
        assert "## The Clarity Editor" in board
        assert "Data Engineering" in board


class TestTemplateFiles:
    def test_templates_generated_from_methodology(self, sample_extraction, sample_identity):
        methodology = MethodologyExtraction(
            output_templates=[
                OutputTemplate(
                    name="Analysis Report",
                    when_to_use="For data analysis deliverables",
                    template="## Summary\n## Findings\n## Recommendations",
                ),
            ],
        )
        generator = SkillFolderGenerator()
        result = generator.generate(sample_extraction, sample_identity, methodology=methodology)

        assert "templates/analysis-report.md" in result.supplementary_files
        tmpl = result.supplementary_files["templates/analysis-report.md"]
        assert "# Analysis Report" in tmpl
        assert "For data analysis deliverables" in tmpl
        assert "## Summary" in tmpl

    def test_templates_section_in_orchestrator(self, sample_extraction, sample_identity):
        methodology = MethodologyExtraction(
            output_templates=[
                OutputTemplate(name="Report", template="## Report\n..."),
            ],
        )
        generator = SkillFolderGenerator()
        result = generator.generate(sample_extraction, sample_identity, methodology=methodology)

        assert "## Templates" in result.skill_md
        assert "`templates/`" in result.skill_md

    def test_no_templates_section_without_methodology(self, sample_extraction, sample_identity):
        generator = SkillFolderGenerator()
        result = generator.generate(sample_extraction, sample_identity)

        assert "## Templates" not in result.skill_md


class TestExampleFiles:
    def test_good_examples_from_user(self, sample_extraction, sample_identity):
        generator = SkillFolderGenerator()
        result = generator.generate(
            sample_extraction, sample_identity,
            user_examples="Here is a sample ETL pipeline design doc...",
        )

        assert "examples/good/work-samples.md" in result.supplementary_files
        examples = result.supplementary_files["examples/good/work-samples.md"]
        assert "sample ETL pipeline design doc" in examples

    def test_no_good_examples_without_user_input(self, sample_extraction, sample_identity):
        generator = SkillFolderGenerator()
        result = generator.generate(sample_extraction, sample_identity)

        assert "examples/good/work-samples.md" not in result.supplementary_files

    def test_anti_patterns_always_generated(self, sample_extraction, sample_identity):
        generator = SkillFolderGenerator()
        result = generator.generate(sample_extraction, sample_identity)

        anti = result.supplementary_files["examples/bad/anti-patterns.md"]
        assert "# Anti-Patterns" in anti
        assert "Avoid" in anti


class TestAntiPatternsFile:
    def test_anti_patterns_from_quality_criteria(self, sample_extraction, sample_identity):
        methodology = MethodologyExtraction(
            quality_criteria=[
                QualityCriterion(criterion="Data-backed claims"),
            ],
        )
        generator = SkillFolderGenerator()
        result = generator.generate(sample_extraction, sample_identity, methodology=methodology)
        anti = result.supplementary_files["examples/bad/anti-patterns.md"]

        assert "Data-backed claims" in anti

    def test_anti_patterns_fallback(self, sample_extraction, sample_identity):
        generator = SkillFolderGenerator()
        result = generator.generate(sample_extraction, sample_identity)
        anti = result.supplementary_files["examples/bad/anti-patterns.md"]

        assert "Data Engineering" in anti
        assert "senior" in anti


class TestSkillMdWithReferences:
    def test_no_references_returns_skill_md(self, sample_extraction, sample_identity):
        result = SkillFolderResult(
            skill_name="test", skill_md="# Test\n", supplementary_files={},
        )
        assert result.skill_md_with_references() == "# Test\n"

    def test_only_appends_references_dir(self, sample_extraction, sample_identity):
        """Structured files (instructions/, eval/, etc.) should NOT appear in references."""
        generator = SkillFolderGenerator()
        result = generator.generate(sample_extraction, sample_identity)

        md = result.skill_md_with_references()
        # No "Reference Files" section since there are no references/ files
        assert "## Reference Files" not in md

    def test_appends_user_uploaded_references(self):
        result = SkillFolderResult(
            skill_name="test",
            skill_md="# Test\n\n---\n*Generated by AgentForge*\n",
            supplementary_files={
                "instructions/voice.md": "...",
                "references/user-doc.md": "uploaded content",
            },
        )
        md = result.skill_md_with_references()
        assert "## Reference Files" in md
        assert "User Doc" in md
        # Should not include instructions/ files
        assert "voice.md" not in md.split("## Reference Files")[1]


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
        # Should still have supplementary files
        assert "instructions/voice.md" in result.supplementary_files

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

        assert "## Identity" in result.skill_md
        # No personality modifiers when no traits defined
        assert "### Personality Modifiers" not in result.skill_md

    def test_no_responsibilities_skips_workflows_in_methodology(self):
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
        meth = result.supplementary_files["instructions/methodology.md"]

        assert "## Workflows" not in meth

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
