"""LLM-powered methodology extraction from role extraction results.

Converts the 'what' (responsibilities, skills) into the 'how' (heuristics,
templates, trigger-technique mappings, quality criteria).
"""

from __future__ import annotations

from agentforge.extraction.prompts import (
    METHODOLOGY_PROMPT,
    METHODOLOGY_SYSTEM_PROMPT,
    METHODOLOGY_USER_CONTEXT_EMPTY,
    METHODOLOGY_USER_CONTEXT_WITH_EXAMPLES,
)
from agentforge.llm.client import LLMClient
from agentforge.models.extracted_skills import (
    ExtractionResult,
    MethodologyExtraction,
)


class MethodologyExtractor:
    """Extracts actionable methodology from extraction results via a second LLM call."""

    def __init__(self, client: LLMClient | None = None):
        self.client = client or LLMClient()

    def extract(
        self,
        extraction: ExtractionResult,
        user_examples: str = "",
        user_frameworks: str = "",
    ) -> MethodologyExtraction:
        """Extract methodology from extraction results.

        Args:
            extraction: The initial skill/role extraction.
            user_examples: Optional user-provided work samples or examples.
            user_frameworks: Optional user-provided frameworks and methodologies.
        """
        # Build responsibilities list
        resp_text = "\n".join(
            f"- {r}" for r in extraction.responsibilities
        ) or "- (none extracted)"

        # Build skills summary
        skills_text = "\n".join(
            f"- {s.name} ({s.category.value}, {s.proficiency.value}): {s.context}"
            for s in extraction.skills[:20]
        ) or "- (none extracted)"

        # Build user context section (truncate to prevent prompt abuse)
        _MAX_USER_INPUT_CHARS = 10_000
        examples_stripped = user_examples.strip()[:_MAX_USER_INPUT_CHARS]
        frameworks_stripped = user_frameworks.strip()[:_MAX_USER_INPUT_CHARS]
        if examples_stripped or frameworks_stripped:
            user_context = METHODOLOGY_USER_CONTEXT_WITH_EXAMPLES.format(
                examples=examples_stripped or "(none provided)",
                frameworks=frameworks_stripped or "(none provided)",
            )
        else:
            user_context = METHODOLOGY_USER_CONTEXT_EMPTY

        prompt = METHODOLOGY_PROMPT.format(
            title=extraction.role.title,
            seniority=extraction.role.seniority.value,
            domain=extraction.role.domain,
            purpose=extraction.role.purpose,
            responsibilities=resp_text,
            skills=skills_text,
            user_context=user_context,
        )

        return self.client.extract_structured(
            prompt=prompt,
            output_schema=MethodologyExtraction,
            system=METHODOLOGY_SYSTEM_PROMPT,
        )
