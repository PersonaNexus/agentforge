"""Guardrail auditor: validate SKILL.md content against a safety checklist and auto-inject missing guardrails."""

from __future__ import annotations

import re

from pydantic import BaseModel, Field


class GuardrailCheck(BaseModel):
    """A single guardrail check definition."""

    id: str
    name: str
    category: str
    required: bool
    domain_specific: bool


class GuardrailResult(BaseModel):
    """Result of evaluating a single guardrail check."""

    check: GuardrailCheck
    passed: bool
    evidence: str
    recommendation: str


class GuardrailReport(BaseModel):
    """Complete guardrail audit report."""

    results: list[GuardrailResult] = Field(default_factory=list)
    passed_count: int = 0
    failed_count: int = 0
    score: float = 0.0
    critical_failures: list[GuardrailResult] = Field(default_factory=list)
    overall_passed: bool = False


# ---------------------------------------------------------------------------
# Checklist definitions
# ---------------------------------------------------------------------------

_UNIVERSAL_CHECKS: list[tuple[str, str, str, list[str]]] = [
    ("no_fabrication", "No Fabrication", "safety",
     ["fabricat", "hallucin", "never invent", "make up", "do not guess"]),
    ("scope_boundary", "Scope Boundaries", "scope",
     ["in scope", "out of scope", "in-scope", "out-of-scope", "boundary", "boundaries", "do not act outside"]),
    ("escalation_path", "Escalation Path", "escalation",
     ["defer to human", "escalat", "hand off", "refer to", "human judgment", "human review"]),
    ("error_handling", "Error Handling", "behavior",
     ["error", "unknown", "fail", "unable to", "cannot determine", "if unsure"]),
    ("confidence_signals", "Confidence Signals", "safety",
     ["uncertain", "confidence", "not sure", "limitation", "acknowledge", "caveat"]),
    ("no_harmful_content", "No Harmful Content", "safety",
     ["harmful", "unethical", "misleading", "never generate harmful", "inappropriate"]),
]

_DOMAIN_CHECKS: list[tuple[str, list[str], str, str, list[str]]] = [
    ("no_financial_advice", ["finance", "banking", "investment"],
     "No Financial Advice", "safety",
     ["financial advice", "investment advice", "not a financial advisor", "tax advice"]),
    ("no_medical_diagnosis", ["health", "medical", "clinical"],
     "No Medical Diagnosis", "safety",
     ["medical advice", "diagnos", "prescri", "not a doctor", "medical professional"]),
    ("no_legal_advice", ["legal", "law", "compliance"],
     "No Legal Advice", "safety",
     ["legal advice", "not a lawyer", "legal counsel", "legal professional"]),
    ("data_privacy", ["data", "engineer", "analytics"],
     "Data Privacy", "data",
     ["personal data", "pii", "sensitive data", "privacy", "confidential", "data protection"]),
    ("no_bias", ["hr", "recruit", "hiring", "people"],
     "No Bias", "safety",
     ["bias", "discriminat", "fair", "equitable", "inclusive"]),
    ("no_vuln_disclosure", ["security", "infosec", "cyber"],
     "No Vulnerability Disclosure", "safety",
     ["vulnerabilit", "exploit", "responsible disclosure", "security issue"]),
]

_FIX_TEMPLATES: dict[str, str] = {
    "no_fabrication": (
        "- **No Fabrication:** Never fabricate or hallucinate information. "
        "If uncertain, explicitly state limitations rather than guessing."
    ),
    "scope_boundary": (
        "- **Scope Boundary:** Stay within the defined scope of this role. "
        "Do not act outside areas of expertise or authorization."
    ),
    "escalation_path": (
        "- **Escalation:** Defer to human judgment for decisions that require "
        "authority, nuanced context, or carry significant consequences."
    ),
    "error_handling": (
        "- **Error Handling:** When encountering errors or unknown situations, "
        "report them clearly rather than proceeding with assumptions."
    ),
    "confidence_signals": (
        "- **Confidence Signals:** Acknowledge uncertainty and limitations. "
        "Clearly distinguish between confident recommendations and speculative suggestions."
    ),
    "no_harmful_content": (
        "- **No Harmful Content:** Never generate harmful, misleading, or "
        "unethical content under any circumstances."
    ),
    "no_financial_advice": (
        "- **No Financial Advice:** Do not provide investment, tax, or financial "
        "planning advice. Defer to qualified financial professionals."
    ),
    "no_medical_diagnosis": (
        "- **No Medical Diagnosis:** Do not diagnose conditions or prescribe "
        "treatments. Defer to qualified medical professionals."
    ),
    "no_legal_advice": (
        "- **No Legal Advice:** Do not provide legal counsel or opinions. "
        "Defer to qualified legal professionals."
    ),
    "data_privacy": (
        "- **Data Privacy:** Handle personal and sensitive data with care. "
        "Never expose PII or confidential information."
    ),
    "no_bias": (
        "- **No Bias:** Avoid discriminatory language and ensure fair, equitable "
        "treatment in all assessments and recommendations."
    ),
    "no_vuln_disclosure": (
        "- **Responsible Disclosure:** Do not publicly disclose vulnerability "
        "details. Follow responsible disclosure practices."
    ),
}


# ---------------------------------------------------------------------------
# Auditor
# ---------------------------------------------------------------------------


class GuardrailAuditor:
    """Validates SKILL.md content against a comprehensive guardrail checklist."""

    def _build_checklist(self, domain: str) -> list[tuple[GuardrailCheck, list[str]]]:
        """Build the checklist of checks + keywords for the given domain."""
        checklist: list[tuple[GuardrailCheck, list[str]]] = []

        # Universal checks
        for check_id, name, category, keywords in _UNIVERSAL_CHECKS:
            check = GuardrailCheck(
                id=check_id,
                name=name,
                category=category,
                required=True,
                domain_specific=False,
            )
            checklist.append((check, keywords))

        # Domain-specific checks
        domain_lower = domain.lower()
        for check_id, domain_keywords, name, category, keywords in _DOMAIN_CHECKS:
            if any(dk in domain_lower for dk in domain_keywords):
                check = GuardrailCheck(
                    id=check_id,
                    name=name,
                    category=category,
                    required=False,
                    domain_specific=True,
                )
                checklist.append((check, keywords))

        return checklist

    @staticmethod
    def _search_keywords(text: str, keywords: list[str]) -> str:
        """Search text (case-insensitive) for any keyword. Return evidence snippet or empty string."""
        text_lower = text.lower()
        for keyword in keywords:
            idx = text_lower.find(keyword.lower())
            if idx != -1:
                start = max(0, idx - 40)
                end = min(len(text), idx + len(keyword) + 40)
                return text[start:end].strip()
        return ""

    def audit(self, skill_md: str, domain: str = "general") -> GuardrailReport:
        """Audit SKILL.md against guardrail checklist."""
        checklist = self._build_checklist(domain)
        results: list[GuardrailResult] = []

        for check, keywords in checklist:
            evidence = self._search_keywords(skill_md, keywords)
            if evidence:
                result = GuardrailResult(
                    check=check,
                    passed=True,
                    evidence=evidence,
                    recommendation="",
                )
            else:
                template = _FIX_TEMPLATES.get(check.id, "")
                result = GuardrailResult(
                    check=check,
                    passed=False,
                    evidence="",
                    recommendation=f"Add guardrail: {template}" if template else f"Add a {check.name} guardrail.",
                )
            results.append(result)

        passed_count = sum(1 for r in results if r.passed)
        failed_count = len(results) - passed_count
        total = len(results)
        score = passed_count / total if total > 0 else 0.0
        critical_failures = [r for r in results if not r.passed and r.check.required]
        overall_passed = len(critical_failures) == 0

        return GuardrailReport(
            results=results,
            passed_count=passed_count,
            failed_count=failed_count,
            score=score,
            critical_failures=critical_failures,
            overall_passed=overall_passed,
        )

    def fix(self, skill_md: str, report: GuardrailReport) -> str:
        """Auto-inject missing guardrails into SKILL.md."""
        failed_checks = [r for r in report.results if not r.passed]
        if not failed_checks:
            return skill_md

        # Build injection lines
        lines_to_inject: list[str] = []
        for result in failed_checks:
            template = _FIX_TEMPLATES.get(result.check.id)
            if template:
                lines_to_inject.append(template)

        if not lines_to_inject:
            return skill_md

        injection_block = "\n".join(lines_to_inject)

        # Check for existing guardrails or scope section
        guardrails_pattern = re.compile(r"^## Guardrails", re.MULTILINE)
        scope_pattern = re.compile(r"^## Scope & Boundaries", re.MULTILINE)

        guardrails_match = guardrails_pattern.search(skill_md)
        scope_match = scope_pattern.search(skill_md)

        if guardrails_match:
            # Append after the Guardrails heading content
            insert_pos = self._find_section_end(skill_md, guardrails_match.start())
            return skill_md[:insert_pos] + "\n" + injection_block + "\n" + skill_md[insert_pos:]
        elif scope_match:
            # Append after the Scope & Boundaries section
            insert_pos = self._find_section_end(skill_md, scope_match.start())
            return skill_md[:insert_pos] + "\n" + injection_block + "\n" + skill_md[insert_pos:]
        else:
            # Create a new ## Guardrails section before the last ## section
            last_section = self._find_last_section(skill_md)
            if last_section is not None:
                new_section = f"\n## Guardrails\n\n{injection_block}\n\n"
                return skill_md[:last_section] + new_section + skill_md[last_section:]
            else:
                # No sections at all — append at end
                return skill_md + f"\n\n## Guardrails\n\n{injection_block}\n"

    @staticmethod
    def _find_section_end(text: str, section_start: int) -> int:
        """Find the end of a section (just before the next ## heading or EOF)."""
        next_heading = re.search(r"\n## ", text[section_start + 1:])
        if next_heading:
            return section_start + 1 + next_heading.start()
        return len(text)

    @staticmethod
    def _find_last_section(text: str) -> int | None:
        """Find the start position of the last ## section."""
        matches = list(re.finditer(r"^## ", text, re.MULTILINE))
        if matches:
            return matches[-1].start()
        return None
