"""Skill linter: validate structural integrity, semantic coherence, and trait consistency in SKILL.md files."""

from __future__ import annotations

import re

from pydantic import BaseModel


class LintIssue(BaseModel):
    """A single lint finding."""

    rule: str
    severity: str
    section: str
    message: str
    suggestion: str


class LintReport(BaseModel):
    """Aggregated lint results."""

    issues: list[LintIssue]
    error_count: int
    warning_count: int
    info_count: int
    passed: bool


# Expected sections — at least 3 must be present.
_EXPECTED_SECTIONS = {
    "Personality Profile",
    "Key Responsibilities",
    "Technical Skills",
    "Soft Skills",
    "Domain Knowledge",
    "Tools & Platforms",
    "Automation Assessment",
}

# Contradictory trait pairs: ((trait_a, threshold_a), (trait_b, threshold_b), message)
_TRAIT_CONTRADICTIONS: list[tuple[tuple[str, float], tuple[str, float], str]] = [
    (
        ("directness", 0.8),
        ("empathy", 0.8),
        "High directness (>80%) and high empathy (>80%) can create conflicting communication signals — "
        "the agent may oscillate between blunt feedback and over-accommodating language.",
    ),
    (
        ("rigor", 0.8),
        ("creativity", 0.8),
        "High rigor (>80%) and high creativity (>80%) pull in opposite directions — "
        "strict process adherence conflicts with free-form ideation.",
    ),
    (
        ("humor", 0.7),
        ("rigor", 0.9),
        "High humor (>70%) with very high rigor (>90%) is an unusual combination — "
        "casual tone may undermine the authoritative precision expected from a rigorous agent.",
    ),
    (
        ("verbosity", 0.8),
        ("directness", 0.8),
        "High verbosity (>80%) and high directness (>80%) conflict — "
        "direct communicators are concise by nature, while verbose agents produce lengthy output.",
    ),
]


class SkillLinter:
    """Lint a SKILL.md file for structural and semantic issues."""

    def lint(self, skill_md: str) -> LintReport:
        """Run all lint checks and return a report."""
        issues: list[LintIssue] = []
        self._check_frontmatter(skill_md, issues)
        self._check_sections(skill_md, issues)
        self._check_traits(skill_md, issues)
        self._check_automation_mismatch(skill_md, issues)
        self._check_scope_overlap(skill_md, issues)
        return self._build_report(issues)

    # ------------------------------------------------------------------
    # Parsing helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_sections(skill_md: str) -> list[tuple[str, str]]:
        """Split *skill_md* into ``(name, content)`` tuples.

        Recognises YAML frontmatter (between ``---`` delimiters) and
        ``## `` markdown headings as section boundaries.
        """
        sections: list[tuple[str, str]] = []
        lines = skill_md.split("\n")

        # Extract frontmatter
        if lines and lines[0].strip() == "---":
            end_idx = None
            for i in range(1, len(lines)):
                if lines[i].strip() == "---":
                    end_idx = i
                    break
            if end_idx is not None:
                fm_text = "\n".join(lines[1:end_idx])
                sections.append(("Frontmatter", fm_text))
                lines = lines[end_idx + 1 :]

        # Split remaining by ## headings
        current_name = "Header"
        current_lines: list[str] = []

        for line in lines:
            if line.startswith("## "):
                if current_lines or current_name != "Header":
                    sections.append((current_name, "\n".join(current_lines)))
                current_name = line[3:].strip()
                current_lines = []
            else:
                current_lines.append(line)

        if current_lines or current_name != "Header":
            sections.append((current_name, "\n".join(current_lines)))

        return sections

    @staticmethod
    def _extract_traits(skill_md: str) -> dict[str, float]:
        """Parse **Trait** (XX%) patterns from the Personality Profile section."""
        traits: dict[str, float] = {}
        # Isolate Personality Profile section
        pattern = re.compile(
            r"## Personality Profile\b(.*?)(?=\n## |\Z)", re.DOTALL
        )
        match = pattern.search(skill_md)
        if not match:
            return traits

        section_text = match.group(1)
        trait_pattern = re.compile(r"\*\*(.+?)\*\*\s*\((\d+)%\)")
        for m in trait_pattern.finditer(section_text):
            name = m.group(1).strip().lower().replace(" ", "_")
            value = int(m.group(2)) / 100.0
            traits[name] = value

        return traits

    @staticmethod
    def _build_report(issues: list[LintIssue]) -> LintReport:
        error_count = sum(1 for i in issues if i.severity == "error")
        warning_count = sum(1 for i in issues if i.severity == "warning")
        info_count = sum(1 for i in issues if i.severity == "info")
        return LintReport(
            issues=issues,
            error_count=error_count,
            warning_count=warning_count,
            info_count=info_count,
            passed=error_count == 0,
        )

    # ------------------------------------------------------------------
    # Structural checks
    # ------------------------------------------------------------------

    def _check_frontmatter(self, skill_md: str, issues: list[LintIssue]) -> None:
        lines = skill_md.split("\n")
        # Check opening ---
        if not lines or lines[0].strip() != "---":
            issues.append(
                LintIssue(
                    rule="missing-frontmatter",
                    severity="error",
                    section="Frontmatter",
                    message="SKILL.md must begin with YAML frontmatter delimited by '---'.",
                    suggestion="Add a frontmatter block at the top: ---\\nname: ...\\ndescription: ...\\n---",
                )
            )
            return

        # Check closing ---
        end_idx = None
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                end_idx = i
                break
        if end_idx is None:
            issues.append(
                LintIssue(
                    rule="missing-frontmatter",
                    severity="error",
                    section="Frontmatter",
                    message="Frontmatter opening '---' found but no closing '---' detected.",
                    suggestion="Add a closing '---' after the frontmatter fields.",
                )
            )
            return

        fm_text = "\n".join(lines[1:end_idx])

        # Check for name: field
        if not re.search(r"^name\s*:", fm_text, re.MULTILINE):
            issues.append(
                LintIssue(
                    rule="frontmatter-name",
                    severity="error",
                    section="Frontmatter",
                    message="Frontmatter is missing the required 'name:' field.",
                    suggestion="Add 'name: <role title>' to the frontmatter block.",
                )
            )

        # Check for description: field
        if not re.search(r"^description\s*:", fm_text, re.MULTILINE):
            issues.append(
                LintIssue(
                    rule="frontmatter-description",
                    severity="error",
                    section="Frontmatter",
                    message="Frontmatter is missing the required 'description:' field.",
                    suggestion="Add 'description: <brief role description>' to the frontmatter block.",
                )
            )

    def _check_sections(self, skill_md: str, issues: list[LintIssue]) -> None:
        sections = self._parse_sections(skill_md)
        section_names = {name for name, _ in sections}

        # Check expected sections
        found = section_names & _EXPECTED_SECTIONS
        if len(found) < 3:
            missing = _EXPECTED_SECTIONS - section_names
            issues.append(
                LintIssue(
                    rule="missing-section",
                    severity="warning",
                    section="Document",
                    message=(
                        f"Only {len(found)} of the expected sections found. "
                        f"Missing: {', '.join(sorted(missing))}."
                    ),
                    suggestion="Ensure the SKILL.md includes at least 3 of the standard sections.",
                )
            )

        # Check for empty sections
        for idx, (name, content) in enumerate(sections):
            if name in ("Frontmatter", "Header"):
                continue
            non_blank = [line for line in content.split("\n") if line.strip()]
            if len(non_blank) < 2:
                issues.append(
                    LintIssue(
                        rule="empty-section",
                        severity="warning",
                        section=name,
                        message=f"Section '{name}' has fewer than 2 non-blank lines of content.",
                        suggestion=f"Add meaningful content to the '{name}' section or remove it.",
                    )
                )

    # ------------------------------------------------------------------
    # Semantic checks
    # ------------------------------------------------------------------

    def _check_traits(self, skill_md: str, issues: list[LintIssue]) -> None:
        traits = self._extract_traits(skill_md)
        if not traits:
            return

        for (trait_a, thresh_a), (trait_b, thresh_b), message in _TRAIT_CONTRADICTIONS:
            val_a = traits.get(trait_a)
            val_b = traits.get(trait_b)
            if val_a is not None and val_b is not None:
                if val_a > thresh_a and val_b > thresh_b:
                    issues.append(
                        LintIssue(
                            rule="trait-contradiction",
                            severity="warning",
                            section="Personality Profile",
                            message=message,
                            suggestion=(
                                f"Consider lowering either '{trait_a}' or '{trait_b}' "
                                "to reduce conflicting behavioural signals."
                            ),
                        )
                    )

    def _check_automation_mismatch(self, skill_md: str, issues: list[LintIssue]) -> None:
        # Parse automation potential percentage
        auto_match = re.search(r"Automation Potential[:\s]*(\d+)%", skill_md)
        if not auto_match:
            return
        auto_pct = int(auto_match.group(1))
        if auto_pct <= 70:
            return

        # Count [Required] badges in Soft Skills section
        pattern = re.compile(
            r"## Soft Skills\b(.*?)(?=\n## |\Z)", re.DOTALL
        )
        ss_match = pattern.search(skill_md)
        if not ss_match:
            return

        required_count = len(re.findall(r"\[Required\]", ss_match.group(1), re.IGNORECASE))
        if required_count >= 2:
            issues.append(
                LintIssue(
                    rule="automation-mismatch",
                    severity="warning",
                    section="Automation Assessment",
                    message=(
                        f"Automation potential is {auto_pct}% but the Soft Skills section "
                        f"lists {required_count} required skills. High-automation roles "
                        "typically need fewer human soft skills."
                    ),
                    suggestion=(
                        "Re-evaluate the automation potential or reduce the number of "
                        "required soft skills to match the expected automation level."
                    ),
                )
            )

    # ------------------------------------------------------------------
    # Coherence checks
    # ------------------------------------------------------------------

    def _check_scope_overlap(self, skill_md: str, issues: list[LintIssue]) -> None:
        sections = self._parse_sections(skill_md)
        section_map = {name: content for name, content in sections}

        primary_content = section_map.get("Primary Scope")
        secondary_content = section_map.get("Secondary Scope")
        if primary_content is None or secondary_content is None:
            return

        primary_items = self._extract_list_items(primary_content)
        secondary_items = self._extract_list_items(secondary_content)

        for p_item in primary_items:
            p_words = set(p_item.lower().split())
            if not p_words:
                continue
            for s_item in secondary_items:
                s_words = set(s_item.lower().split())
                if not s_words:
                    continue
                overlap = len(p_words & s_words)
                total = min(len(p_words), len(s_words))
                if total > 0 and overlap / total > 0.6:
                    issues.append(
                        LintIssue(
                            rule="scope-overlap",
                            severity="warning",
                            section="Primary Scope / Secondary Scope",
                            message=(
                                f"Overlapping scope items detected: "
                                f"'{p_item}' (primary) and '{s_item}' (secondary) "
                                f"share >60% word overlap."
                            ),
                            suggestion=(
                                "Move the item to one scope only, or differentiate "
                                "the descriptions to clarify the distinction."
                            ),
                        )
                    )

    @staticmethod
    def _extract_list_items(content: str) -> list[str]:
        """Extract markdown list items (lines starting with ``- `` or ``* ``)."""
        items: list[str] = []
        for line in content.split("\n"):
            stripped = line.strip()
            if stripped.startswith("- ") or stripped.startswith("* "):
                items.append(stripped[2:].strip())
        return items
