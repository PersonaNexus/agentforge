"""Skill refinement: merge user edits into extraction/methodology and regenerate."""

from __future__ import annotations

from typing import Any

from agentforge.models.extracted_skills import (
    ExtractionResult,
    Heuristic,
    MethodologyExtraction,
    OutputTemplate,
    QualityCriterion,
    TriggerTechniqueMapping,
)


class SkillRefiner:
    """Merges user-provided gap edits into extraction + methodology data.

    Each edit category maps to a specific merge strategy that enriches
    the data without discarding what was already extracted.
    """

    def merge(
        self,
        extraction: ExtractionResult,
        methodology: MethodologyExtraction | None,
        edits: dict[str, str],
    ) -> tuple[ExtractionResult, MethodologyExtraction]:
        """Merge user edits into extraction and methodology.

        Args:
            extraction: Original extraction result.
            methodology: Original methodology (may be None).
            edits: Dict of {gap_category: user_text}.

        Returns:
            Updated (extraction, methodology) tuple.
        """
        meth = methodology.model_copy(deep=True) if methodology else MethodologyExtraction()
        ext = extraction.model_copy(deep=True)

        for category, text in edits.items():
            text = text.strip()
            if not text:
                continue

            if category == "methodology":
                self._merge_methodology(meth, text, ext)
            elif category == "triggers":
                self._merge_triggers(meth, text)
            elif category == "templates":
                self._merge_templates(meth, text)
            elif category == "quality":
                self._merge_quality(meth, text)
            elif category == "domain":
                self._merge_domain(ext, text)
            elif category == "persona":
                self._merge_persona(ext, text)
            elif category == "scope":
                self._merge_scope(ext, text)
            elif category == "examples":
                self._merge_examples(meth, text)
            elif category == "frameworks":
                self._merge_frameworks(meth, text)

        return ext, meth

    # ------------------------------------------------------------------
    # Merge strategies per category
    # ------------------------------------------------------------------

    def _merge_methodology(
        self, meth: MethodologyExtraction, text: str, ext: ExtractionResult
    ) -> None:
        """Parse user text as heuristics and add them."""
        # Split on double newlines or numbered items for multiple heuristics
        entries = self._split_entries(text)
        for entry in entries:
            meth.heuristics.append(Heuristic(
                trigger=f"When {entry[:80].rstrip('.')}",
                procedure=entry,
                source_responsibility="User-provided refinement",
            ))

    def _merge_triggers(self, meth: MethodologyExtraction, text: str) -> None:
        """Parse user text as trigger → technique mappings."""
        entries = self._split_entries(text)
        for entry in entries:
            # Try to split on → or ->
            parts = None
            for sep in ["→", "->", "—", ":"]:
                if sep in entry:
                    parts = entry.split(sep, 1)
                    break
            if parts and len(parts) == 2:
                meth.trigger_mappings.append(TriggerTechniqueMapping(
                    trigger_pattern=parts[0].strip(),
                    technique=parts[1].strip(),
                ))
            else:
                meth.trigger_mappings.append(TriggerTechniqueMapping(
                    trigger_pattern=entry.strip(),
                    technique="Apply standard approach",
                ))

    def _merge_templates(self, meth: MethodologyExtraction, text: str) -> None:
        """Add user text as an output template."""
        # Treat entire text as a single template
        name = "User-Provided Template"
        # Try to extract a name from the first line
        lines = text.strip().splitlines()
        if lines:
            first = lines[0].strip().lstrip("#").strip()
            if len(first) < 80 and first:
                name = first
                text = "\n".join(lines[1:]).strip() or text

        meth.output_templates.append(OutputTemplate(
            name=name,
            when_to_use="As the primary output format for this skill",
            template=text,
        ))

    def _merge_quality(self, meth: MethodologyExtraction, text: str) -> None:
        """Parse user text as quality criteria."""
        entries = self._split_entries(text)
        for entry in entries:
            meth.quality_criteria.append(QualityCriterion(
                criterion=entry.strip().rstrip("."),
                description="User-provided quality standard",
            ))

    def _merge_domain(self, ext: ExtractionResult, text: str) -> None:
        """Apply domain context as genai_application to domain skills."""
        from agentforge.models.extracted_skills import SkillCategory

        domain_skills = [
            s for s in ext.skills
            if s.category == SkillCategory.DOMAIN and not s.genai_application
        ]
        # Apply the text to all domain skills without genai context
        for skill in domain_skills:
            skill.genai_application = text

    def _merge_persona(self, ext: ExtractionResult, text: str) -> None:
        """Interpret user persona description as trait adjustments."""
        text_lower = text.lower()
        # Simple keyword-based trait inference
        trait_keywords = {
            "warmth": ["warm", "friendly", "approachable", "casual", "informal"],
            "verbosity": ["detailed", "verbose", "thorough", "comprehensive"],
            "assertiveness": ["assertive", "confident", "decisive", "direct"],
            "humor": ["humor", "funny", "witty", "lighthearted"],
            "empathy": ["empathetic", "understanding", "compassionate", "supportive"],
            "directness": ["direct", "blunt", "straightforward", "concise", "brief"],
            "rigor": ["rigorous", "precise", "methodical", "analytical", "structured"],
            "creativity": ["creative", "innovative", "imaginative", "flexible"],
            "epistemic_humility": ["humble", "open-minded", "uncertain", "nuanced"],
            "patience": ["patient", "calm", "measured", "deliberate"],
        }

        for trait_name, keywords in trait_keywords.items():
            current = getattr(ext.suggested_traits, trait_name, None)
            if current is not None:
                continue  # Don't override already-set traits
            for kw in keywords:
                if kw in text_lower:
                    setattr(ext.suggested_traits, trait_name, 0.8)
                    break

        # Also check for "low" variants
        low_keywords = {
            "warmth": ["formal", "professional", "impersonal"],
            "verbosity": ["concise", "brief", "terse", "succinct"],
            "humor": ["serious", "no humor", "strictly professional"],
        }
        for trait_name, keywords in low_keywords.items():
            current = getattr(ext.suggested_traits, trait_name, None)
            if current is not None:
                continue
            for kw in keywords:
                if kw in text_lower:
                    setattr(ext.suggested_traits, trait_name, 0.2)
                    break

    def _merge_scope(self, ext: ExtractionResult, text: str) -> None:
        """Parse user text as scope secondary / guardrails."""
        entries = self._split_entries(text)
        if not ext.role.scope_secondary:
            ext.role.scope_secondary = []
        ext.role.scope_secondary.extend(entries)

    def _merge_examples(self, meth: MethodologyExtraction, text: str) -> None:
        """Treat user examples as output templates."""
        self._merge_templates(meth, text)

    def _merge_frameworks(self, meth: MethodologyExtraction, text: str) -> None:
        """Parse user frameworks as heuristics."""
        entries = self._split_entries(text)
        for entry in entries:
            meth.heuristics.append(Heuristic(
                trigger=f"When applying {entry[:60].rstrip('.')}",
                procedure=f"Follow the {entry} framework/methodology",
                source_responsibility="User-provided framework",
            ))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _split_entries(text: str) -> list[str]:
        """Split user text into individual entries.

        Handles:
          - Numbered lists (1. foo, 2. bar)
          - Bullet lists (- foo, * bar)
          - Double-newline separated paragraphs
          - Comma-separated items (if short)
        """
        import re

        lines = text.strip()
        if not lines:
            return []

        # Try numbered/bulleted lists first
        list_pattern = re.compile(r"^\s*(?:\d+[\.\)]\s*|[-*•]\s+)", re.MULTILINE)
        items = list_pattern.split(lines)
        items = [item.strip() for item in items if item.strip()]
        if len(items) >= 2:
            return items

        # Try double-newline split
        paragraphs = re.split(r"\n\s*\n", lines)
        paragraphs = [p.strip() for p in paragraphs if p.strip()]
        if len(paragraphs) >= 2:
            return paragraphs

        # Try comma-separated (only if entries are short)
        if "," in lines and len(lines) < 500:
            parts = [p.strip() for p in lines.split(",") if p.strip()]
            if all(len(p) < 100 for p in parts) and len(parts) >= 2:
                return parts

        # Return as single entry
        return [lines]
