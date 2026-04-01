"""Tests for the GuardrailAuditor."""

from __future__ import annotations

import pytest

from agentforge.analysis.guardrail_auditor import (
    GuardrailAuditor,
    GuardrailCheck,
    GuardrailReport,
    GuardrailResult,
)
from agentforge.generation.skill_file import SkillFileGenerator
from tests.conftest import _make_sample_extraction


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_full_guardrails_md() -> str:
    """Return a SKILL.md string that contains keywords for all universal checks."""
    return """\
# Senior Data Engineer

## Purpose
Design, build, and maintain scalable data infrastructure.

## Guardrails

- Never fabricate or hallucinate information. Do not guess or make up data.
- Stay in scope and respect out-of-scope boundaries. Do not act outside your role.
- Escalate to human judgment when uncertain. Defer to human review for critical decisions.
- Handle errors gracefully. If unsure, report the error rather than proceeding.
- Acknowledge uncertainty and limitations. Provide confidence caveats when appropriate.
- Never generate harmful or misleading content. Avoid unethical outputs.

## Output Format
Provide structured responses.
"""


def _make_minimal_md() -> str:
    """Return a very minimal SKILL.md with no guardrail keywords."""
    return """\
# Some Role

## Purpose
Do things.

## Tasks
- Task 1
- Task 2
"""


def _make_finance_md() -> str:
    """Return a SKILL.md for a finance domain with financial advice guardrails."""
    return _make_full_guardrails_md() + "\n- Not a financial advisor. Do not provide investment advice or tax advice.\n"


# ---------------------------------------------------------------------------
# TestGuardrailChecklist
# ---------------------------------------------------------------------------

class TestGuardrailChecklist:
    """Tests for the checklist-building logic."""

    def setup_method(self) -> None:
        self.auditor = GuardrailAuditor()

    def test_universal_checks_exist(self) -> None:
        checklist = self.auditor._build_checklist("general")
        ids = [c.id for c, _ in checklist]
        assert "no_fabrication" in ids
        assert "scope_boundary" in ids
        assert "escalation_path" in ids
        assert "error_handling" in ids
        assert "confidence_signals" in ids
        assert "no_harmful_content" in ids
        assert len(checklist) == 6

    def test_domain_checks_for_finance(self) -> None:
        checklist = self.auditor._build_checklist("finance")
        ids = [c.id for c, _ in checklist]
        assert "no_financial_advice" in ids

    def test_domain_checks_for_health(self) -> None:
        checklist = self.auditor._build_checklist("health")
        ids = [c.id for c, _ in checklist]
        assert "no_medical_diagnosis" in ids

    def test_domain_checks_for_legal(self) -> None:
        checklist = self.auditor._build_checklist("legal")
        ids = [c.id for c, _ in checklist]
        assert "no_legal_advice" in ids

    def test_domain_checks_for_data(self) -> None:
        checklist = self.auditor._build_checklist("data")
        ids = [c.id for c, _ in checklist]
        assert "data_privacy" in ids

    def test_domain_checks_for_hr(self) -> None:
        checklist = self.auditor._build_checklist("hiring")
        ids = [c.id for c, _ in checklist]
        assert "no_bias" in ids

    def test_domain_checks_for_security(self) -> None:
        checklist = self.auditor._build_checklist("security")
        ids = [c.id for c, _ in checklist]
        assert "no_vuln_disclosure" in ids

    def test_general_domain_no_domain_specific(self) -> None:
        checklist = self.auditor._build_checklist("general")
        domain_specific = [c for c, _ in checklist if c.domain_specific]
        assert len(domain_specific) == 0


# ---------------------------------------------------------------------------
# TestAuditReport
# ---------------------------------------------------------------------------

class TestAuditReport:
    """Tests for audit report generation."""

    def setup_method(self) -> None:
        self.auditor = GuardrailAuditor()

    def test_all_pass(self) -> None:
        md = _make_full_guardrails_md()
        report = self.auditor.audit(md, domain="general")
        assert report.overall_passed is True
        assert report.failed_count == 0
        assert report.passed_count == 6

    def test_missing_guardrails(self) -> None:
        md = _make_minimal_md()
        report = self.auditor.audit(md, domain="general")
        assert report.overall_passed is False
        assert report.failed_count > 0

    def test_score_calculation(self) -> None:
        md = _make_full_guardrails_md()
        report = self.auditor.audit(md, domain="general")
        expected_score = report.passed_count / (report.passed_count + report.failed_count)
        assert report.score == pytest.approx(expected_score)

    def test_critical_failures(self) -> None:
        md = _make_minimal_md()
        report = self.auditor.audit(md, domain="general")
        # All universal checks are required, so critical_failures should contain only required fails
        for failure in report.critical_failures:
            assert failure.check.required is True
            assert failure.passed is False

    def test_evidence_extraction(self) -> None:
        md = _make_full_guardrails_md()
        report = self.auditor.audit(md, domain="general")
        for result in report.results:
            if result.passed:
                assert result.evidence != ""

    def test_realistic_skill_md(self) -> None:
        extraction = _make_sample_extraction()
        generator = SkillFileGenerator()
        skill_md = generator.generate(extraction)
        report = self.auditor.audit(skill_md, domain="Data Engineering")
        # Realistic skill should pass at least some checks but likely not all
        assert report.passed_count > 0
        assert len(report.results) > 0

    def test_empty_input(self) -> None:
        report = self.auditor.audit("", domain="general")
        assert report.overall_passed is False
        assert report.passed_count == 0
        assert report.failed_count == 6


# ---------------------------------------------------------------------------
# TestAutoFix
# ---------------------------------------------------------------------------

class TestAutoFix:
    """Tests for the auto-fix functionality."""

    def setup_method(self) -> None:
        self.auditor = GuardrailAuditor()

    def test_fix_injects_guardrails(self) -> None:
        md = _make_minimal_md()
        report = self.auditor.audit(md, domain="general")
        fixed = self.auditor.fix(md, report)
        assert "No Fabrication" in fixed
        assert "Escalation" in fixed

    def test_fix_creates_guardrails_section(self) -> None:
        md = _make_minimal_md()
        report = self.auditor.audit(md, domain="general")
        fixed = self.auditor.fix(md, report)
        assert "## Guardrails" in fixed

    def test_fix_appends_to_existing_section(self) -> None:
        md = """\
# Role

## Guardrails

- Existing guardrail.

## Output
Done.
"""
        report = self.auditor.audit(md, domain="general")
        fixed = self.auditor.fix(md, report)
        # The existing guardrail should still be present
        assert "Existing guardrail" in fixed
        # New guardrails should be injected
        assert "No Fabrication" in fixed
        # Should NOT create a second Guardrails section
        assert fixed.count("## Guardrails") == 1

    def test_fix_preserves_existing_content(self) -> None:
        md = _make_minimal_md()
        report = self.auditor.audit(md, domain="general")
        fixed = self.auditor.fix(md, report)
        # All original content should still be present
        assert "# Some Role" in fixed
        assert "## Purpose" in fixed
        assert "Do things." in fixed
        assert "Task 1" in fixed

    def test_fixed_skill_passes_audit(self) -> None:
        md = _make_minimal_md()
        report = self.auditor.audit(md, domain="general")
        fixed = self.auditor.fix(md, report)
        re_report = self.auditor.audit(fixed, domain="general")
        # After fix, all previously failed checks should now pass
        for orig_result in report.results:
            if not orig_result.passed:
                matching = [r for r in re_report.results if r.check.id == orig_result.check.id]
                assert len(matching) == 1
                assert matching[0].passed is True, f"{orig_result.check.id} still fails after fix"

    def test_fix_no_change_when_all_pass(self) -> None:
        md = _make_full_guardrails_md()
        report = self.auditor.audit(md, domain="general")
        fixed = self.auditor.fix(md, report)
        assert fixed == md


# ---------------------------------------------------------------------------
# TestDomainDetection
# ---------------------------------------------------------------------------

class TestDomainDetection:
    """Tests for domain-specific check matching."""

    def setup_method(self) -> None:
        self.auditor = GuardrailAuditor()

    def test_domain_keywords_matched(self) -> None:
        checklist = self.auditor._build_checklist("Data Engineering")
        ids = [c.id for c, _ in checklist]
        assert "data_privacy" in ids
