"""Tests for JD anonymization."""

from __future__ import annotations

import pytest

from agentforge.ingestion.anonymizer import (
    AnonymizationResult,
    anonymize_text_simple,
)


class TestAnonymizationResult:
    def test_model_validates(self):
        result = AnonymizationResult(
            anonymized_text="A large fintech company is hiring.",
            replacements=[{"original": "Mastercard", "replacement": "a large fintech company"}],
        )
        assert "fintech" in result.anonymized_text
        assert len(result.replacements) == 1

    def test_empty_replacements(self):
        result = AnonymizationResult(
            anonymized_text="No companies mentioned.",
            replacements=[],
        )
        assert result.replacements == []


class TestSimpleAnonymizer:
    def test_removes_email(self):
        text = "Apply to jobs@mastercard.com for more info."
        result = anonymize_text_simple(text)
        assert "mastercard.com" not in result
        assert "[email removed]" in result

    def test_removes_urls(self):
        text = "See https://careers.mastercard.com/apply for details."
        result = anonymize_text_simple(text)
        assert "careers.mastercard.com" not in result
        assert "[link removed]" in result

    def test_preserves_plain_text(self):
        text = "5+ years of data engineering experience required."
        result = anonymize_text_simple(text)
        assert result == text


class TestAnonymizeStage:
    """Test the pipeline stage integration."""

    def test_skips_when_not_requested(self):
        from agentforge.pipeline.stages import AnonymizeStage

        stage = AnonymizeStage()
        context = {"jd": "some jd", "llm_client": "some_client"}
        # anonymize flag not set — should be a no-op
        result = stage.run(context)
        assert result["jd"] == "some jd"

    def test_skips_without_llm_client(self):
        from agentforge.pipeline.stages import AnonymizeStage

        stage = AnonymizeStage()
        context = {"jd": "some jd", "anonymize": True}
        result = stage.run(context)
        assert result["jd"] == "some jd"
