"""Anonymize company and personal names in job description text.

Uses an LLM to detect and replace identifiable entities (company names,
people, specific locations) with generic equivalents that preserve the
industry context. For example: "Mastercard" → "a large fintech company".
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field


class AnonymizationResult(BaseModel):
    """Result of anonymizing a job description."""

    anonymized_text: str = Field(
        description="The full job description text with all identifying information replaced by generic equivalents."
    )
    replacements: list[dict[str, str]] = Field(
        default_factory=list,
        description="List of replacements made, each with 'original' and 'replacement' keys.",
    )


# Common patterns that suggest company names or identifiers
_BOILERPLATE_PATTERN = re.compile(
    r"(?:equal\s+opportunity|eoe|e\.o\.e\.|affirmative\s+action)",
    re.IGNORECASE,
)

_SYSTEM_PROMPT = """\
You are a text anonymizer for job descriptions. Your task is to replace all \
identifying information while preserving the role's context and industry.

Rules:
1. Replace company names with a generic description preserving industry and scale.
   - "Mastercard" → "a large fintech company"
   - "Google" → "a major technology company"
   - "Acme Health Inc." → "a mid-size healthcare company"
2. Replace specific people's names with generic titles.
   - "Report to John Smith, VP of Engineering" → "Report to the VP of Engineering"
3. Replace specific office addresses with region only.
   - "123 Main St, San Francisco, CA" → "the San Francisco Bay Area"
   - Keep the city/region, remove street addresses.
4. Remove or generalize any URLs, email addresses, or application links.
5. Keep job title, responsibilities, requirements, skills, and qualifications exactly as-is.
6. Keep industry/domain terminology intact — only anonymize identifying entities.
7. Preserve the original formatting (markdown, bullets, sections, etc.).
8. If you are unsure whether something is an identifier, err on the side of replacing it.
"""


def anonymize_text(text: str, llm_client: Any) -> AnonymizationResult:
    """Anonymize identifiable entities in job description text using an LLM.

    Args:
        text: Raw job description text.
        llm_client: An LLMClient instance for making structured calls.

    Returns:
        AnonymizationResult with anonymized text and list of replacements.
    """
    prompt = (
        "Anonymize the following job description. Replace all company names, "
        "people's names, specific addresses, URLs, and other identifying "
        "information with generic equivalents.\n\n"
        "---\n\n"
        f"{text}\n\n"
        "---\n\n"
        "Return the fully anonymized text and a list of replacements you made."
    )

    return llm_client.extract_structured(
        prompt=prompt,
        output_schema=AnonymizationResult,
        system=_SYSTEM_PROMPT,
        max_tokens=8192,
    )


def anonymize_text_simple(text: str) -> str:
    """Quick regex-based anonymization for obvious patterns.

    This is a fallback for when no LLM client is available. It catches
    common patterns like email addresses and URLs but won't detect
    company names without an LLM.
    """
    # Remove email addresses
    result = re.sub(
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
        "[email removed]",
        text,
    )
    # Remove URLs
    result = re.sub(
        r"https?://[^\s)<>]+",
        "[link removed]",
        result,
    )
    return result
