"""Tests for the SKILL.md linter."""

from __future__ import annotations

import re
import textwrap

import pytest

from agentforge.analysis.skill_linter import LintIssue, LintReport, SkillLinter
from agentforge.generation.skill_file import SkillFileGenerator
from tests.conftest import _make_sample_extraction


@pytest.fixture
def linter() -> SkillLinter:
    return SkillLinter()


@pytest.fixture
def realistic_skill_md() -> str:
    extraction = _make_sample_extraction()
    return SkillFileGenerator().generate(extraction)


# ── helpers ──────────────────────────────────────────────────────────


def _has_rule(report: LintReport, rule: str) -> bool:
    return any(i.rule == rule for i in report.issues)


def _make_frontmatter(name: str = "Test Role", description: str = "A test role") -> str:
    return f"---\nname: {name}\ndescription: {description}\n---\n"


def _make_personality_section(**traits: int) -> str:
    """Build a Personality Profile section with given trait percentages."""
    lines = ["## Personality Profile\n"]
    for trait_name, pct in traits.items():
        display_name = trait_name.replace("_", " ").title()
        lines.append(f"**{display_name}** ({pct}%): Description of {display_name}.")
    return "\n".join(lines)


def _make_skill_md_with_sections(*section_names: str, frontmatter: bool = True) -> str:
    """Build a minimal SKILL.md with named sections containing placeholder content."""
    parts: list[str] = []
    if frontmatter:
        parts.append(_make_frontmatter())
    parts.append("# Test Skill\n")
    for name in section_names:
        parts.append(f"## {name}\n")
        parts.append("Content line one.\nContent line two.\n")
    return "\n".join(parts)


# =====================================================================
# Structural checks
# =====================================================================


class TestStructuralChecks:
    def test_valid_frontmatter_no_error(self, linter: SkillLinter, realistic_skill_md: str) -> None:
        report = linter.lint(realistic_skill_md)
        assert not _has_rule(report, "missing-frontmatter")

    def test_missing_frontmatter(self, linter: SkillLinter) -> None:
        content = "# No Frontmatter\n\n## Section\nSome content here.\nAnother line.\n"
        report = linter.lint(content)
        assert _has_rule(report, "missing-frontmatter")
        issue = next(i for i in report.issues if i.rule == "missing-frontmatter")
        assert issue.severity == "error"

    def test_missing_frontmatter_name(self, linter: SkillLinter) -> None:
        content = "---\ndescription: A role\n---\n## Section\nContent line.\nAnother line.\n"
        report = linter.lint(content)
        assert _has_rule(report, "frontmatter-name")
        issue = next(i for i in report.issues if i.rule == "frontmatter-name")
        assert issue.severity == "error"

    def test_missing_frontmatter_description(self, linter: SkillLinter) -> None:
        content = "---\nname: Test Role\n---\n## Section\nContent line.\nAnother line.\n"
        report = linter.lint(content)
        assert _has_rule(report, "frontmatter-description")
        issue = next(i for i in report.issues if i.rule == "frontmatter-description")
        assert issue.severity == "error"

    def test_has_expected_sections(self, linter: SkillLinter, realistic_skill_md: str) -> None:
        report = linter.lint(realistic_skill_md)
        assert not _has_rule(report, "missing-section")

    def test_missing_sections(self, linter: SkillLinter) -> None:
        content = _make_frontmatter() + "# Just a header\n\n## Random Section\nLine one.\nLine two.\n"
        report = linter.lint(content)
        assert _has_rule(report, "missing-section")

    def test_empty_section(self, linter: SkillLinter) -> None:
        content = _make_frontmatter() + "## Empty\n\n## Next\nContent line one.\nContent line two.\n"
        report = linter.lint(content)
        assert _has_rule(report, "empty-section")
        issue = next(i for i in report.issues if i.rule == "empty-section")
        assert issue.section == "Empty"

    def test_non_empty_sections_ok(self, linter: SkillLinter, realistic_skill_md: str) -> None:
        report = linter.lint(realistic_skill_md)
        assert not _has_rule(report, "empty-section")


# =====================================================================
# Trait contradictions
# =====================================================================


class TestTraitContradictions:
    def test_no_contradiction_normal_traits(self, linter: SkillLinter, realistic_skill_md: str) -> None:
        report = linter.lint(realistic_skill_md)
        assert not _has_rule(report, "trait-contradiction")

    def test_high_directness_high_empathy(self, linter: SkillLinter) -> None:
        content = (
            _make_frontmatter()
            + _make_personality_section(directness=85, empathy=90)
            + "\n## Key Responsibilities\nLine 1.\nLine 2.\n"
            + "## Technical Skills\nLine 1.\nLine 2.\n"
            + "## Soft Skills\nLine 1.\nLine 2.\n"
        )
        report = linter.lint(content)
        assert _has_rule(report, "trait-contradiction")
        issues = [i for i in report.issues if i.rule == "trait-contradiction"]
        messages = " ".join(i.message for i in issues)
        assert "directness" in messages.lower()
        assert "empathy" in messages.lower()

    def test_high_rigor_high_creativity(self, linter: SkillLinter) -> None:
        content = (
            _make_frontmatter()
            + _make_personality_section(rigor=90, creativity=85)
            + "\n## Key Responsibilities\nLine 1.\nLine 2.\n"
            + "## Technical Skills\nLine 1.\nLine 2.\n"
            + "## Soft Skills\nLine 1.\nLine 2.\n"
        )
        report = linter.lint(content)
        assert _has_rule(report, "trait-contradiction")
        issues = [i for i in report.issues if i.rule == "trait-contradiction"]
        messages = " ".join(i.message for i in issues)
        assert "rigor" in messages.lower()
        assert "creativity" in messages.lower()

    def test_moderate_traits_no_warning(self, linter: SkillLinter) -> None:
        content = (
            _make_frontmatter()
            + _make_personality_section(directness=55, empathy=60, rigor=50, creativity=55)
            + "\n## Key Responsibilities\nLine 1.\nLine 2.\n"
            + "## Technical Skills\nLine 1.\nLine 2.\n"
            + "## Soft Skills\nLine 1.\nLine 2.\n"
        )
        report = linter.lint(content)
        assert not _has_rule(report, "trait-contradiction")


# =====================================================================
# Automation mismatch
# =====================================================================


class TestAutomationMismatch:
    def test_low_automation_no_warning(self, linter: SkillLinter) -> None:
        content = (
            _make_frontmatter()
            + "## Automation Assessment\nAutomation Potential: 40%\n\n"
            + "## Soft Skills\n- Communication [Required]\n- Empathy [Required]\n- Leadership [Required]\n"
            + "## Key Responsibilities\nLine 1.\nLine 2.\n"
            + "## Technical Skills\nLine 1.\nLine 2.\n"
        )
        report = linter.lint(content)
        assert not _has_rule(report, "automation-mismatch")

    def test_high_automation_many_soft_skills(self, linter: SkillLinter) -> None:
        content = (
            _make_frontmatter()
            + "## Automation Assessment\nAutomation Potential: 85%\n\n"
            + "## Soft Skills\n- Communication [Required]\n- Empathy [Required]\n- Leadership [Required]\n"
            + "## Key Responsibilities\nLine 1.\nLine 2.\n"
            + "## Technical Skills\nLine 1.\nLine 2.\n"
        )
        report = linter.lint(content)
        assert _has_rule(report, "automation-mismatch")
        issue = next(i for i in report.issues if i.rule == "automation-mismatch")
        assert issue.severity == "warning"

    def test_high_automation_few_soft_skills(self, linter: SkillLinter) -> None:
        content = (
            _make_frontmatter()
            + "## Automation Assessment\nAutomation Potential: 85%\n\n"
            + "## Soft Skills\n- Communication [Required]\n- Empathy [Nice to Have]\n"
            + "## Key Responsibilities\nLine 1.\nLine 2.\n"
            + "## Technical Skills\nLine 1.\nLine 2.\n"
        )
        report = linter.lint(content)
        assert not _has_rule(report, "automation-mismatch")


# =====================================================================
# Scope overlap
# =====================================================================


class TestScopeOverlap:
    def test_no_overlap(self, linter: SkillLinter) -> None:
        content = (
            _make_frontmatter()
            + "## Primary Scope\n- ETL pipeline design\n- Data warehouse architecture\n\n"
            + "## Secondary Scope\n- ML model deployment\n- Team mentoring\n\n"
            + "## Key Responsibilities\nLine 1.\nLine 2.\n"
            + "## Technical Skills\nLine 1.\nLine 2.\n"
            + "## Soft Skills\nLine 1.\nLine 2.\n"
        )
        report = linter.lint(content)
        assert not _has_rule(report, "scope-overlap")

    def test_overlapping_scope(self, linter: SkillLinter) -> None:
        content = (
            _make_frontmatter()
            + "## Primary Scope\n- ETL pipeline design and maintenance\n- Data quality monitoring\n\n"
            + "## Secondary Scope\n- ETL pipeline design and maintenance\n- Team mentoring\n\n"
            + "## Key Responsibilities\nLine 1.\nLine 2.\n"
            + "## Technical Skills\nLine 1.\nLine 2.\n"
            + "## Soft Skills\nLine 1.\nLine 2.\n"
        )
        report = linter.lint(content)
        assert _has_rule(report, "scope-overlap")


# =====================================================================
# Overall report
# =====================================================================


class TestOverall:
    def test_realistic_skill_md_passes(self, linter: SkillLinter, realistic_skill_md: str) -> None:
        report = linter.lint(realistic_skill_md)
        assert report.passed is True
        assert report.error_count == 0

    def test_report_counts(self, linter: SkillLinter) -> None:
        # Construct content that triggers 1 error and 1 warning
        content = "# No frontmatter\n\n## Only One Section\nSome content.\nMore content.\n"
        report = linter.lint(content)
        # Should have at least 1 error (missing-frontmatter) and 1 warning (missing-section)
        assert report.error_count == sum(1 for i in report.issues if i.severity == "error")
        assert report.warning_count == sum(1 for i in report.issues if i.severity == "warning")
        assert report.info_count == sum(1 for i in report.issues if i.severity == "info")
        assert report.error_count >= 1
        assert report.passed is False
