"""Tests for prompt differ."""

from __future__ import annotations

import pytest

from agentforge.analysis.prompt_differ import PromptDiffer, PromptDiffReport, TraitDiff
from agentforge.generation.skill_file import SkillFileGenerator
from tests.conftest import _make_sample_extraction


def _make_skill_md() -> str:
    return SkillFileGenerator().generate(_make_sample_extraction())


class TestSectionDiff:
    def test_identical_files(self):
        md = _make_skill_md()
        differ = PromptDiffer()
        report = differ.diff(md, md)
        assert report.sections_added == 0
        assert report.sections_removed == 0
        assert report.sections_changed == 0
        assert report.total_token_delta == 0
        assert all(s.status == "unchanged" for s in report.sections)

    def test_added_section(self):
        old = "## Existing\nContent here\n"
        new = "## Existing\nContent here\n\n## New Section\nNew content\n"
        differ = PromptDiffer()
        report = differ.diff(old, new)
        assert report.sections_added == 1
        added = [s for s in report.sections if s.status == "added"]
        assert len(added) == 1
        assert added[0].section == "New Section"

    def test_removed_section(self):
        old = "## Section A\nContent A\n\n## Section B\nContent B\n"
        new = "## Section A\nContent A\n"
        differ = PromptDiffer()
        report = differ.diff(old, new)
        assert report.sections_removed == 1
        removed = [s for s in report.sections if s.status == "removed"]
        assert len(removed) == 1
        assert removed[0].section == "Section B"

    def test_changed_section(self):
        old = "## Section\nOriginal content\n"
        new = "## Section\nModified content with more text\n"
        differ = PromptDiffer()
        report = differ.diff(old, new)
        assert report.sections_changed == 1
        changed = [s for s in report.sections if s.status == "changed"]
        assert len(changed) == 1
        assert "modified" in changed[0].change_summary.lower() or "changed" in changed[0].change_summary.lower()

    def test_total_token_delta_positive(self):
        old = "## A\nShort\n"
        new = "## A\nShort\n\n## B\n" + "x" * 400 + "\n"
        differ = PromptDiffer()
        report = differ.diff(old, new)
        assert report.total_token_delta > 0

    def test_total_token_delta_negative(self):
        old = "## A\n" + "x" * 400 + "\n\n## B\nMore content\n"
        new = "## A\nShort\n"
        differ = PromptDiffer()
        report = differ.diff(old, new)
        assert report.total_token_delta < 0

    def test_frontmatter_diffed(self):
        old = "---\nname: old\n---\n## Body\nContent\n"
        new = "---\nname: new-name\ndescription: added\n---\n## Body\nContent\n"
        differ = PromptDiffer()
        report = differ.diff(old, new)
        fm = [s for s in report.sections if s.section == "Frontmatter"]
        assert len(fm) == 1
        assert fm[0].status == "changed"


class TestTraitDiff:
    def test_no_trait_changes(self):
        md = _make_skill_md()
        differ = PromptDiffer()
        report = differ.diff(md, md)
        assert len(report.trait_changes) == 0

    def test_trait_value_changed(self):
        old = "## Personality Profile\n\n- **Rigor** (85%): Detail-oriented\n"
        new = "## Personality Profile\n\n- **Rigor** (60%): Balanced\n"
        differ = PromptDiffer()
        report = differ.diff(old, new)
        assert len(report.trait_changes) == 1
        assert report.trait_changes[0].trait == "rigor"
        assert report.trait_changes[0].old_value == 0.85
        assert report.trait_changes[0].new_value == 0.60
        assert report.trait_changes[0].delta == -0.25

    def test_trait_added(self):
        old = "## Personality Profile\n\n- **Rigor** (85%): High\n"
        new = "## Personality Profile\n\n- **Rigor** (85%): High\n- **Humor** (40%): Moderate\n"
        differ = PromptDiffer()
        report = differ.diff(old, new)
        added = [t for t in report.trait_changes if t.trait == "humor"]
        assert len(added) == 1
        assert added[0].old_value is None
        assert added[0].new_value == 0.40

    def test_trait_removed(self):
        old = "## Personality Profile\n\n- **Rigor** (85%): High\n- **Humor** (40%): Moderate\n"
        new = "## Personality Profile\n\n- **Rigor** (85%): High\n"
        differ = PromptDiffer()
        report = differ.diff(old, new)
        removed = [t for t in report.trait_changes if t.trait == "humor"]
        assert len(removed) == 1
        assert removed[0].old_value == 0.40
        assert removed[0].new_value is None


class TestEmpty:
    def test_both_empty(self):
        differ = PromptDiffer()
        report = differ.diff("", "")
        assert report.total_token_delta == 0
        assert report.sections_added == 0

    def test_old_empty_new_has_content(self):
        differ = PromptDiffer()
        report = differ.diff("", "## New\nContent\n")
        assert report.sections_added >= 1
        assert report.total_token_delta > 0


class TestRealisticDiff:
    def test_realistic_modification(self):
        """Modify a realistic SKILL.md and verify diff detects changes."""
        md = _make_skill_md()
        modified = md.replace("## Personality Profile", "## Personality Profile\n\nExtra guidance here.")
        differ = PromptDiffer()
        report = differ.diff(md, modified)
        assert report.sections_changed >= 1
        assert report.total_token_delta != 0
