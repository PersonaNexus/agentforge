"""Prompt size monitoring: measure, break down, and flag bloat in generated prompts."""

from __future__ import annotations

import re
from collections import Counter

import yaml
from pydantic import BaseModel, Field


def _estimate_tokens(text: str) -> int:
    """Estimate token count using chars // 4 approximation."""
    return len(text) // 4


class SectionMetrics(BaseModel):
    """Size metrics for a single prompt section."""

    name: str
    char_count: int
    line_count: int
    estimated_tokens: int
    percentage: float = Field(0.0, description="Percentage of total prompt")


class SizeVerdict(BaseModel):
    """An actionable finding about prompt size."""

    section: str
    severity: str = Field(..., description="ok, warning, or bloated")
    message: str


class PromptSizeReport(BaseModel):
    """Complete prompt size analysis report."""

    total_chars: int
    total_lines: int
    total_estimated_tokens: int
    sections: list[SectionMetrics] = Field(default_factory=list)
    verdicts: list[SizeVerdict] = Field(default_factory=list)
    overall_assessment: str = Field(
        "lean", description="lean, moderate, or bloated"
    )


# ---------------------------------------------------------------------------
# Default thresholds
# ---------------------------------------------------------------------------

_DEFAULT_TOKEN_BUDGET = 8000
_BLOATED_TOKEN_BUDGET = 15000
_SECTION_DOMINANCE_WARNING = 0.35
_SECTION_DOMINANCE_BLOATED = 0.50
_PERSONALITY_TOKEN_WARNING = 2000
_EMBEDDED_JSON_TOKEN_WARNING = 3000


class PromptSizeAnalyzer:
    """Analyzes generated prompt content for size and bloat.

    Works with SKILL.md files (parsed by ``## `` headings) and
    identity YAML files (parsed by top-level keys).
    """

    def __init__(
        self,
        token_budget: int = _DEFAULT_TOKEN_BUDGET,
        bloated_budget: int = _BLOATED_TOKEN_BUDGET,
    ) -> None:
        self.token_budget = token_budget
        self.bloated_budget = bloated_budget

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze_skill_md(self, content: str) -> PromptSizeReport:
        """Analyze a SKILL.md file for size and bloat."""
        sections = self._parse_skill_md_sections(content)
        return self._build_report(content, sections, source="skill_md")

    def analyze_identity_yaml(self, content: str) -> PromptSizeReport:
        """Analyze an identity YAML file for size and bloat."""
        sections = self._parse_yaml_sections(content)
        return self._build_report(content, sections, source="identity_yaml")

    def analyze_combined(
        self,
        skill_md: str,
        identity_yaml: str | None = None,
    ) -> PromptSizeReport:
        """Analyze skill + identity prompts together."""
        sections = self._parse_skill_md_sections(skill_md)

        if identity_yaml:
            yaml_sections = self._parse_yaml_sections(identity_yaml)
            # Prefix yaml section names to distinguish
            for sec_name, sec_text in yaml_sections:
                sections.append((f"Identity: {sec_name}", sec_text))

        combined = skill_md
        if identity_yaml:
            combined = skill_md + "\n" + identity_yaml

        return self._build_report(combined, sections, source="combined")

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    def _parse_skill_md_sections(
        self, content: str
    ) -> list[tuple[str, str]]:
        """Split SKILL.md into (name, text) sections.

        Recognises YAML frontmatter (between ``---`` delimiters) and
        ``## `` markdown headings as section boundaries.
        """
        sections: list[tuple[str, str]] = []
        lines = content.split("\n")

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
                # Flush previous section
                if current_lines or current_name != "Header":
                    sections.append((current_name, "\n".join(current_lines)))
                current_name = line[3:].strip()
                current_lines = []
            else:
                current_lines.append(line)

        # Flush last section
        if current_lines or current_name != "Header":
            sections.append((current_name, "\n".join(current_lines)))

        return sections

    def _parse_yaml_sections(
        self, content: str
    ) -> list[tuple[str, str]]:
        """Split identity YAML into sections by top-level keys."""
        sections: list[tuple[str, str]] = []
        try:
            data = yaml.safe_load(content)
        except yaml.YAMLError:
            # If YAML is invalid, treat as single section
            sections.append(("yaml_content", content))
            return sections

        if not isinstance(data, dict):
            sections.append(("yaml_content", content))
            return sections

        for key, value in data.items():
            section_yaml = yaml.dump(
                {key: value},
                default_flow_style=False,
                sort_keys=False,
                allow_unicode=True,
            )
            sections.append((key, section_yaml))

        return sections

    # ------------------------------------------------------------------
    # Report building
    # ------------------------------------------------------------------

    def _build_report(
        self,
        full_content: str,
        sections: list[tuple[str, str]],
        source: str,
    ) -> PromptSizeReport:
        """Build a PromptSizeReport from parsed sections."""
        total_chars = len(full_content)
        total_lines = full_content.count("\n") + (1 if full_content else 0)
        total_tokens = _estimate_tokens(full_content)

        section_metrics: list[SectionMetrics] = []
        for name, text in sections:
            chars = len(text)
            lines = text.count("\n") + (1 if text else 0)
            tokens = _estimate_tokens(text)
            pct = (chars / total_chars * 100) if total_chars > 0 else 0.0
            section_metrics.append(
                SectionMetrics(
                    name=name,
                    char_count=chars,
                    line_count=lines,
                    estimated_tokens=tokens,
                    percentage=round(pct, 1),
                )
            )

        verdicts = self._evaluate(
            total_tokens, section_metrics, sections, source
        )

        # Determine overall assessment
        severities = [v.severity for v in verdicts]
        if "bloated" in severities:
            overall = "bloated"
        elif "warning" in severities:
            overall = "moderate"
        else:
            overall = "lean"

        return PromptSizeReport(
            total_chars=total_chars,
            total_lines=total_lines,
            total_estimated_tokens=total_tokens,
            sections=section_metrics,
            verdicts=verdicts,
            overall_assessment=overall,
        )

    # ------------------------------------------------------------------
    # Bloat evaluation
    # ------------------------------------------------------------------

    def _evaluate(
        self,
        total_tokens: int,
        section_metrics: list[SectionMetrics],
        sections: list[tuple[str, str]],
        source: str,
    ) -> list[SizeVerdict]:
        """Apply bloat-detection heuristics."""
        verdicts: list[SizeVerdict] = []

        # 1. Total token budget
        if total_tokens > self.bloated_budget:
            verdicts.append(SizeVerdict(
                section="total",
                severity="bloated",
                message=(
                    f"Total prompt is ~{total_tokens:,} tokens, exceeding the "
                    f"{self.bloated_budget:,}-token budget. Consider removing "
                    "low-value sections or trimming verbose content."
                ),
            ))
        elif total_tokens > self.token_budget:
            verdicts.append(SizeVerdict(
                section="total",
                severity="warning",
                message=(
                    f"Total prompt is ~{total_tokens:,} tokens, approaching the "
                    f"recommended {self.token_budget:,}-token budget. Review "
                    "sections for content that could be more concise."
                ),
            ))

        # 2. Section dominance (only meaningful with multiple substantial sections)
        has_multiple_sections = len([s for s in section_metrics if s.estimated_tokens > 10]) > 1
        for sm in section_metrics:
            frac = sm.percentage / 100
            if not has_multiple_sections:
                break
            if frac > _SECTION_DOMINANCE_BLOATED:
                verdicts.append(SizeVerdict(
                    section=sm.name,
                    severity="bloated",
                    message=(
                        f"'{sm.name}' is {sm.percentage:.0f}% of the total prompt "
                        f"({sm.estimated_tokens:,} tokens). This section dominates "
                        "the prompt and should be trimmed."
                    ),
                ))
            elif frac > _SECTION_DOMINANCE_WARNING:
                verdicts.append(SizeVerdict(
                    section=sm.name,
                    severity="warning",
                    message=(
                        f"'{sm.name}' is {sm.percentage:.0f}% of the total prompt "
                        f"({sm.estimated_tokens:,} tokens). Consider whether all "
                        "content in this section is necessary."
                    ),
                ))

        # 3. Personality section size
        if source in ("skill_md", "combined"):
            for sm in section_metrics:
                if "personality" in sm.name.lower() or "profile" in sm.name.lower():
                    if sm.estimated_tokens > _PERSONALITY_TOKEN_WARNING:
                        verdicts.append(SizeVerdict(
                            section=sm.name,
                            severity="warning",
                            message=(
                                f"Personality section is ~{sm.estimated_tokens:,} tokens. "
                                "Trait descriptions may be overly verbose — "
                                "consider keeping only the most distinctive traits."
                            ),
                        ))

        # 4. Embedded JSON size
        for sm in section_metrics:
            if "data" in sm.name.lower() and "machine" in sm.name.lower():
                if sm.estimated_tokens > _EMBEDDED_JSON_TOKEN_WARNING:
                    verdicts.append(SizeVerdict(
                        section=sm.name,
                        severity="warning",
                        message=(
                            f"Machine-readable data block is ~{sm.estimated_tokens:,} "
                            "tokens. Consider whether this duplicated data needs "
                            "to be embedded in the prompt."
                        ),
                    ))

        # 5. Duplicate sentences across sections
        dup_verdicts = self._check_duplicates(sections)
        verdicts.extend(dup_verdicts)

        return verdicts

    def _check_duplicates(
        self, sections: list[tuple[str, str]]
    ) -> list[SizeVerdict]:
        """Detect sentences that appear in multiple sections."""
        verdicts: list[SizeVerdict] = []

        # Map sentence → set of section names
        sentence_locations: dict[str, set[str]] = {}
        for name, text in sections:
            sentences = self._extract_sentences(text)
            for sent in sentences:
                sentence_locations.setdefault(sent, set()).add(name)

        # Find duplicates (sentence appears in 2+ sections)
        duplicated_sections: Counter[str] = Counter()
        for sent, locs in sentence_locations.items():
            if len(locs) >= 2:
                for loc in locs:
                    duplicated_sections[loc] += 1

        for section_name, count in duplicated_sections.most_common():
            if count >= 1:
                verdicts.append(SizeVerdict(
                    section=section_name,
                    severity="warning",
                    message=(
                        f"'{section_name}' shares {count} duplicate sentences "
                        "with other sections. Remove redundant content to "
                        "reduce prompt size."
                    ),
                ))

        return verdicts

    @staticmethod
    def _extract_sentences(text: str) -> list[str]:
        """Extract meaningful sentences from text (min 40 chars)."""
        # Split on sentence-ending punctuation
        raw = re.split(r"[.!?]\s+", text)
        sentences: list[str] = []
        for s in raw:
            cleaned = s.strip().strip("*_`#->")
            # Only consider substantial sentences (avoid headings, bullets)
            if len(cleaned) >= 40:
                sentences.append(cleaned.lower())
        return sentences
