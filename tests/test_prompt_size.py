"""Tests for prompt size analyzer."""

from __future__ import annotations

import pytest

from agentforge.analysis.prompt_size_analyzer import (
    PromptSizeAnalyzer,
    PromptSizeReport,
    SectionMetrics,
    _estimate_tokens,
)
from agentforge.generation.identity_generator import IdentityGenerator
from agentforge.generation.skill_file import SkillFileGenerator
from tests.conftest import _make_sample_extraction


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_skill_md() -> str:
    """Generate a realistic SKILL.md from the sample extraction."""
    extraction = _make_sample_extraction()
    gen = SkillFileGenerator()
    return gen.generate(extraction)


def _make_padded_skill_md(extra_chars: int = 0) -> str:
    """Generate SKILL.md with optional padding in a section."""
    base = _make_skill_md()
    if extra_chars:
        padding = "\n" + "x" * extra_chars + "\n"
        # Inject padding into the responsibilities section
        base = base.replace(
            "## Key Responsibilities",
            "## Key Responsibilities" + padding,
        )
    return base


def _make_identity_yaml() -> str:
    extraction = _make_sample_extraction()
    gen = IdentityGenerator()
    _, yaml_str = gen.generate(extraction)
    return yaml_str


# ---------------------------------------------------------------------------
# Token estimation
# ---------------------------------------------------------------------------


class TestTokenEstimation:
    def test_basic_estimation(self):
        assert _estimate_tokens("abcd") == 1
        assert _estimate_tokens("abcdefgh") == 2

    def test_empty_string(self):
        assert _estimate_tokens("") == 0

    def test_realistic_text(self):
        text = "The quick brown fox jumps over the lazy dog."
        tokens = _estimate_tokens(text)
        assert 8 <= tokens <= 15  # ~45 chars / 4 ≈ 11


# ---------------------------------------------------------------------------
# Section parsing
# ---------------------------------------------------------------------------


class TestSectionParsing:
    def test_parses_frontmatter(self):
        content = "---\nname: test\n---\n\n# Title\nBody"
        analyzer = PromptSizeAnalyzer()
        report = analyzer.analyze_skill_md(content)
        section_names = [s.name for s in report.sections]
        assert "Frontmatter" in section_names

    def test_parses_h2_headings(self):
        content = "## Section One\nContent one\n\n## Section Two\nContent two\n"
        analyzer = PromptSizeAnalyzer()
        report = analyzer.analyze_skill_md(content)
        section_names = [s.name for s in report.sections]
        assert "Section One" in section_names
        assert "Section Two" in section_names

    def test_realistic_skill_md_sections(self):
        skill_md = _make_skill_md()
        analyzer = PromptSizeAnalyzer()
        report = analyzer.analyze_skill_md(skill_md)
        section_names = [s.name for s in report.sections]
        # Should have frontmatter + header + multiple ## sections
        assert "Frontmatter" in section_names
        assert len(report.sections) >= 5

    def test_section_names_match_headings(self):
        skill_md = _make_skill_md()
        analyzer = PromptSizeAnalyzer()
        report = analyzer.analyze_skill_md(skill_md)
        section_names = [s.name for s in report.sections]
        # Key sections from SkillFileGenerator
        assert "Personality Profile" in section_names
        assert "Key Responsibilities" in section_names


# ---------------------------------------------------------------------------
# Basic metrics
# ---------------------------------------------------------------------------


class TestBasicMetrics:
    def test_total_char_count(self):
        content = "Hello world"
        analyzer = PromptSizeAnalyzer()
        report = analyzer.analyze_skill_md(content)
        assert report.total_chars == len(content)

    def test_total_line_count(self):
        content = "line1\nline2\nline3"
        analyzer = PromptSizeAnalyzer()
        report = analyzer.analyze_skill_md(content)
        assert report.total_lines == 3

    def test_total_tokens(self):
        content = "a" * 400
        analyzer = PromptSizeAnalyzer()
        report = analyzer.analyze_skill_md(content)
        assert report.total_estimated_tokens == 100

    def test_percentages_sum_roughly_to_100(self):
        skill_md = _make_skill_md()
        analyzer = PromptSizeAnalyzer()
        report = analyzer.analyze_skill_md(skill_md)
        # Percentages may not be exact due to heading lines and separators
        total_pct = sum(s.percentage for s in report.sections)
        # Should be roughly 100% (allow margin for heading/separator chars)
        assert 70 <= total_pct <= 110

    def test_empty_input(self):
        analyzer = PromptSizeAnalyzer()
        report = analyzer.analyze_skill_md("")
        assert report.total_chars == 0
        assert report.total_estimated_tokens == 0
        assert report.overall_assessment == "lean"


# ---------------------------------------------------------------------------
# Bloat detection: total tokens
# ---------------------------------------------------------------------------


class TestTotalTokenBudget:
    def test_lean_prompt(self):
        skill_md = _make_skill_md()
        analyzer = PromptSizeAnalyzer()
        report = analyzer.analyze_skill_md(skill_md)
        # Standard extraction should be well under budget
        assert report.total_estimated_tokens < 8000

    def test_warning_at_budget(self):
        # Create a prompt that exceeds 8000 tokens (~32K chars)
        content = "## Content\n" + "word " * 8000
        analyzer = PromptSizeAnalyzer()
        report = analyzer.analyze_skill_md(content)
        severities = [v.severity for v in report.verdicts if v.section == "total"]
        assert "warning" in severities or "bloated" in severities

    def test_bloated_at_high_budget(self):
        # Create a prompt that exceeds 15000 tokens (~60K chars)
        content = "## Content\n" + "word " * 15000
        analyzer = PromptSizeAnalyzer()
        report = analyzer.analyze_skill_md(content)
        severities = [v.severity for v in report.verdicts if v.section == "total"]
        assert "bloated" in severities

    def test_custom_budget(self):
        content = "## Content\n" + "word " * 2000  # ~10K chars = ~2500 tokens
        analyzer = PromptSizeAnalyzer(token_budget=2000)
        report = analyzer.analyze_skill_md(content)
        severities = [v.severity for v in report.verdicts if v.section == "total"]
        assert "warning" in severities or "bloated" in severities


# ---------------------------------------------------------------------------
# Bloat detection: section dominance
# ---------------------------------------------------------------------------


class TestSectionDominance:
    def test_dominant_section_warning(self):
        # One section is >35% of total, both sections are substantial
        content = "## Small\n" + "y" * 100 + "\n\n## Big\n" + "x" * 1000
        analyzer = PromptSizeAnalyzer()
        report = analyzer.analyze_skill_md(content)
        big_verdicts = [v for v in report.verdicts if v.section == "Big"]
        assert any(v.severity in ("warning", "bloated") for v in big_verdicts)

    def test_balanced_sections_no_warning(self):
        # Multiple sections of similar size
        sections = []
        for i in range(5):
            sections.append(f"## Section {i}\n" + "content " * 50)
        content = "\n\n".join(sections)
        analyzer = PromptSizeAnalyzer()
        report = analyzer.analyze_skill_md(content)
        dominance_verdicts = [
            v for v in report.verdicts
            if "dominates" in v.message or "%" in v.message.split("of the total")[0]
            if v.section != "total"
        ]
        # No section should be flagged as bloated
        assert not any(v.severity == "bloated" for v in dominance_verdicts)


# ---------------------------------------------------------------------------
# Bloat detection: personality section
# ---------------------------------------------------------------------------


class TestPersonalityBloat:
    def test_normal_personality_no_warning(self):
        skill_md = _make_skill_md()
        analyzer = PromptSizeAnalyzer()
        report = analyzer.analyze_skill_md(skill_md)
        personality_verdicts = [
            v for v in report.verdicts
            if "personality" in v.section.lower() or "profile" in v.section.lower()
        ]
        # Normal extraction should not trigger personality warning
        bloated = [v for v in personality_verdicts if "verbose" in v.message.lower()]
        assert len(bloated) == 0

    def test_oversized_personality_warning(self):
        # Inject a huge personality section
        content = (
            "## Header\nShort\n\n"
            "## Personality Profile\n" + "Trait description. " * 2000 + "\n\n"
            "## Skills\nSome skills\n"
        )
        analyzer = PromptSizeAnalyzer()
        report = analyzer.analyze_skill_md(content)
        personality_verdicts = [
            v for v in report.verdicts
            if "personality" in v.message.lower() or "trait" in v.message.lower()
        ]
        assert len(personality_verdicts) > 0


# ---------------------------------------------------------------------------
# Duplicate detection
# ---------------------------------------------------------------------------


class TestDuplicateDetection:
    def test_detects_duplicate_sentences(self):
        shared = "This is a sentence that appears in multiple sections across the document"
        content = (
            f"## Section A\n{shared}.\n\n"
            f"## Section B\n{shared}.\n"
        )
        analyzer = PromptSizeAnalyzer()
        report = analyzer.analyze_skill_md(content)
        dup_verdicts = [v for v in report.verdicts if "duplicate" in v.message.lower()]
        assert len(dup_verdicts) > 0

    def test_no_false_positives_on_short_text(self):
        content = "## A\nHello.\n\n## B\nHello.\n"
        analyzer = PromptSizeAnalyzer()
        report = analyzer.analyze_skill_md(content)
        dup_verdicts = [v for v in report.verdicts if "duplicate" in v.message.lower()]
        # "Hello" is too short (< 40 chars) to be flagged
        assert len(dup_verdicts) == 0


# ---------------------------------------------------------------------------
# Identity YAML analysis
# ---------------------------------------------------------------------------


class TestIdentityYAML:
    def test_parses_yaml_top_level_keys(self):
        yaml_content = _make_identity_yaml()
        analyzer = PromptSizeAnalyzer()
        report = analyzer.analyze_identity_yaml(yaml_content)
        section_names = [s.name for s in report.sections]
        # PersonaNexus identity has these top-level keys
        assert "schema_version" in section_names or "metadata" in section_names
        assert "personality" in section_names
        assert "role" in section_names

    def test_yaml_metrics(self):
        yaml_content = _make_identity_yaml()
        analyzer = PromptSizeAnalyzer()
        report = analyzer.analyze_identity_yaml(yaml_content)
        assert report.total_chars > 0
        assert report.total_estimated_tokens > 0

    def test_invalid_yaml_handled(self):
        analyzer = PromptSizeAnalyzer()
        report = analyzer.analyze_identity_yaml(":::not valid yaml{{{\n")
        assert report.total_chars > 0
        assert len(report.sections) == 1
        assert report.sections[0].name == "yaml_content"


# ---------------------------------------------------------------------------
# Combined analysis
# ---------------------------------------------------------------------------


class TestCombinedAnalysis:
    def test_combined_includes_both(self):
        skill_md = _make_skill_md()
        identity_yaml = _make_identity_yaml()
        analyzer = PromptSizeAnalyzer()
        report = analyzer.analyze_combined(skill_md, identity_yaml)
        section_names = [s.name for s in report.sections]
        # Should have skill sections AND identity sections
        assert any("Identity:" in n for n in section_names)
        assert "Frontmatter" in section_names

    def test_combined_tokens_greater_than_individual(self):
        skill_md = _make_skill_md()
        identity_yaml = _make_identity_yaml()
        analyzer = PromptSizeAnalyzer()
        skill_report = analyzer.analyze_skill_md(skill_md)
        combined_report = analyzer.analyze_combined(skill_md, identity_yaml)
        assert combined_report.total_estimated_tokens > skill_report.total_estimated_tokens

    def test_combined_without_identity(self):
        skill_md = _make_skill_md()
        analyzer = PromptSizeAnalyzer()
        report = analyzer.analyze_combined(skill_md)
        # Should work fine with just skill_md
        assert report.total_chars == len(skill_md)


# ---------------------------------------------------------------------------
# Overall assessment
# ---------------------------------------------------------------------------


class TestOverallAssessment:
    def test_lean_assessment(self):
        content = "## Hello\nShort and sweet."
        analyzer = PromptSizeAnalyzer()
        report = analyzer.analyze_skill_md(content)
        assert report.overall_assessment == "lean"

    def test_moderate_assessment(self):
        # Exceed token budget but not bloated budget
        content = "## Content\n" + "word " * 8000
        analyzer = PromptSizeAnalyzer()
        report = analyzer.analyze_skill_md(content)
        assert report.overall_assessment in ("moderate", "bloated")

    def test_bloated_assessment(self):
        content = "## Content\n" + "word " * 15000
        analyzer = PromptSizeAnalyzer()
        report = analyzer.analyze_skill_md(content)
        assert report.overall_assessment == "bloated"
