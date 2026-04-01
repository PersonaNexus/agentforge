"""Prompt differ: compare two SKILL.md files section-by-section."""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

from agentforge.analysis.prompt_size_analyzer import PromptSizeAnalyzer, _estimate_tokens


class SectionDiff(BaseModel):
    """Diff result for a single section."""

    section: str
    status: str = Field(..., description="added, removed, changed, or unchanged")
    old_size: int = Field(0, description="Token count in old version")
    new_size: int = Field(0, description="Token count in new version")
    change_summary: str = ""


class TraitDiff(BaseModel):
    """Change in a single personality trait."""

    trait: str
    old_value: float | None = None
    new_value: float | None = None
    delta: float = 0.0


class PromptDiffReport(BaseModel):
    """Complete section-by-section diff of two SKILL.md files."""

    sections: list[SectionDiff] = Field(default_factory=list)
    trait_changes: list[TraitDiff] = Field(default_factory=list)
    total_token_delta: int = 0
    sections_added: int = 0
    sections_removed: int = 0
    sections_changed: int = 0


_TRAIT_PATTERN = re.compile(r"\*\*(.+?)\*\*\s*\((\d+)%\)")


class PromptDiffer:
    """Compare two SKILL.md files and report section-level changes."""

    def __init__(self) -> None:
        self._analyzer = PromptSizeAnalyzer()

    def diff(self, old_md: str, new_md: str) -> PromptDiffReport:
        """Diff two SKILL.md files."""
        old_sections = dict(self._analyzer._parse_skill_md_sections(old_md))
        new_sections = dict(self._analyzer._parse_skill_md_sections(new_md))

        all_names = list(dict.fromkeys(list(old_sections) + list(new_sections)))

        section_diffs: list[SectionDiff] = []
        added = removed = changed = 0

        for name in all_names:
            old_text = old_sections.get(name)
            new_text = new_sections.get(name)

            if old_text is None and new_text is not None:
                section_diffs.append(SectionDiff(
                    section=name,
                    status="added",
                    old_size=0,
                    new_size=_estimate_tokens(new_text),
                    change_summary=f"New section added ({_estimate_tokens(new_text)} tokens)",
                ))
                added += 1
            elif old_text is not None and new_text is None:
                section_diffs.append(SectionDiff(
                    section=name,
                    status="removed",
                    old_size=_estimate_tokens(old_text),
                    new_size=0,
                    change_summary=f"Section removed ({_estimate_tokens(old_text)} tokens)",
                ))
                removed += 1
            elif old_text == new_text:
                section_diffs.append(SectionDiff(
                    section=name,
                    status="unchanged",
                    old_size=_estimate_tokens(old_text),
                    new_size=_estimate_tokens(new_text),
                ))
            else:
                old_tokens = _estimate_tokens(old_text)
                new_tokens = _estimate_tokens(new_text)
                delta = new_tokens - old_tokens
                direction = "grew" if delta > 0 else "shrank" if delta < 0 else "same size"
                section_diffs.append(SectionDiff(
                    section=name,
                    status="changed",
                    old_size=old_tokens,
                    new_size=new_tokens,
                    change_summary=f"Content modified ({direction} by {abs(delta)} tokens)",
                ))
                changed += 1

        # Trait-level comparison
        old_traits = self._extract_traits(old_md)
        new_traits = self._extract_traits(new_md)
        trait_changes = self._diff_traits(old_traits, new_traits)

        old_total = _estimate_tokens(old_md)
        new_total = _estimate_tokens(new_md)

        return PromptDiffReport(
            sections=section_diffs,
            trait_changes=trait_changes,
            total_token_delta=new_total - old_total,
            sections_added=added,
            sections_removed=removed,
            sections_changed=changed,
        )

    @staticmethod
    def _extract_traits(content: str) -> dict[str, float]:
        """Extract personality trait values from SKILL.md content."""
        traits: dict[str, float] = {}
        for match in _TRAIT_PATTERN.finditer(content):
            name = match.group(1).strip().lower().replace(" ", "_")
            value = int(match.group(2)) / 100
            traits[name] = value
        return traits

    @staticmethod
    def _diff_traits(
        old: dict[str, float], new: dict[str, float]
    ) -> list[TraitDiff]:
        """Compare two trait dicts."""
        all_traits = sorted(set(old) | set(new))
        diffs: list[TraitDiff] = []
        for trait in all_traits:
            old_val = old.get(trait)
            new_val = new.get(trait)
            if old_val == new_val:
                continue
            delta = (new_val or 0.0) - (old_val or 0.0)
            diffs.append(TraitDiff(
                trait=trait,
                old_value=old_val,
                new_value=new_val,
                delta=round(delta, 2),
            ))
        return diffs
