"""Skill drift detection — compare running agent files against forged spec.

Surfaces:
  - Trait drift (personality values changed)
  - Guardrail additions/removals
  - Spec/runtime file mismatches
  - Recommendations for re-forge or spec sync
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class DriftFinding:
    """A single drift finding between spec and runtime."""

    category: str  # "trait_drift", "guardrail", "file_mismatch", "content_drift"
    description: str
    severity: str = "info"  # "significant", "minor", "info"
    spec_value: str = ""
    runtime_value: str = ""

    def __str__(self) -> str:
        if self.spec_value and self.runtime_value:
            return f"{self.description}: {self.spec_value} → {self.runtime_value}  ({self.severity})"
        return f"{self.description}  ({self.severity})"


@dataclass
class DriftReport:
    """Complete drift analysis between spec and runtime."""

    findings: list[DriftFinding] = field(default_factory=list)
    recommendation: str = ""
    spec_path: str = ""
    runtime_path: str = ""

    @property
    def has_significant_drift(self) -> bool:
        return any(f.severity == "significant" for f in self.findings)

    @property
    def trait_drifts(self) -> list[DriftFinding]:
        return [f for f in self.findings if f.category == "trait_drift"]

    @property
    def guardrail_changes(self) -> list[DriftFinding]:
        return [f for f in self.findings if f.category == "guardrail"]

    @property
    def file_mismatches(self) -> list[DriftFinding]:
        return [f for f in self.findings if f.category == "file_mismatch"]

    def summary(self) -> str:
        sig = sum(1 for f in self.findings if f.severity == "significant")
        minor = sum(1 for f in self.findings if f.severity == "minor")
        return f"{sig} significant, {minor} minor drift(s) detected"


class DriftDetector:
    """Compares a forged spec against runtime agent files."""

    TRAIT_DRIFT_THRESHOLD = 0.1  # ±10% is significant

    def detect(
        self,
        spec_dir: Path,
        runtime_dir: Path,
    ) -> DriftReport:
        """Compare spec directory against runtime directory.

        Args:
            spec_dir: Path to the original forged agent files.
            runtime_dir: Path to the currently running agent files.
        """
        report = DriftReport(
            spec_path=str(spec_dir),
            runtime_path=str(runtime_dir),
        )

        self._check_file_presence(spec_dir, runtime_dir, report)
        self._check_trait_drift(spec_dir, runtime_dir, report)
        self._check_guardrail_drift(spec_dir, runtime_dir, report)
        self._check_content_drift(spec_dir, runtime_dir, report)

        # Generate recommendation
        if report.has_significant_drift:
            report.recommendation = (
                "Recommend: re-forge from updated spec or sync spec to runtime"
            )
        elif report.findings:
            report.recommendation = (
                "Minor drift detected — monitor but no action needed"
            )
        else:
            report.recommendation = "No drift detected — spec and runtime are in sync"

        return report

    def _check_file_presence(
        self, spec_dir: Path, runtime_dir: Path, report: DriftReport
    ) -> None:
        """Check for files present in spec but missing at runtime, and vice versa."""
        spec_files = self._collect_files(spec_dir)
        runtime_files = self._collect_files(runtime_dir)

        spec_rel = set(spec_files.keys())
        runtime_rel = set(runtime_files.keys())

        for missing in spec_rel - runtime_rel:
            report.findings.append(DriftFinding(
                category="file_mismatch",
                description=f"Missing at runtime: {missing} (in spec, not in runtime)",
                severity="significant",
            ))

        for added in runtime_rel - spec_rel:
            report.findings.append(DriftFinding(
                category="file_mismatch",
                description=f"Added at runtime: {added} (not in spec)",
                severity="minor",
            ))

    def _check_trait_drift(
        self, spec_dir: Path, runtime_dir: Path, report: DriftReport
    ) -> None:
        """Compare personality traits between spec and runtime."""
        spec_traits = self._extract_traits(spec_dir)
        runtime_traits = self._extract_traits(runtime_dir)

        if not spec_traits or not runtime_traits:
            return

        all_keys = set(spec_traits.keys()) | set(runtime_traits.keys())
        for key in sorted(all_keys):
            spec_val = spec_traits.get(key)
            runtime_val = runtime_traits.get(key)

            if spec_val is not None and runtime_val is not None:
                diff = abs(spec_val - runtime_val)
                if diff >= self.TRAIT_DRIFT_THRESHOLD:
                    report.findings.append(DriftFinding(
                        category="trait_drift",
                        description=f"Trait drift: {key}",
                        severity="significant" if diff >= 0.15 else "minor",
                        spec_value=f"{spec_val:.2f}",
                        runtime_value=f"{runtime_val:.2f}",
                    ))
            elif spec_val is not None and runtime_val is None:
                report.findings.append(DriftFinding(
                    category="trait_drift",
                    description=f"Trait removed at runtime: {key}",
                    severity="minor",
                    spec_value=f"{spec_val:.2f}",
                ))
            elif runtime_val is not None and spec_val is None:
                report.findings.append(DriftFinding(
                    category="trait_drift",
                    description=f"Trait added at runtime: {key}",
                    severity="minor",
                    runtime_value=f"{runtime_val:.2f}",
                ))

    def _check_guardrail_drift(
        self, spec_dir: Path, runtime_dir: Path, report: DriftReport
    ) -> None:
        """Compare guardrails between spec and runtime SKILL.md/SOUL.md."""
        spec_guardrails = self._extract_guardrails(spec_dir)
        runtime_guardrails = self._extract_guardrails(runtime_dir)

        added = runtime_guardrails - spec_guardrails
        removed = spec_guardrails - runtime_guardrails

        for g in added:
            report.findings.append(DriftFinding(
                category="guardrail",
                description=f"New guardrail: {g} (added manually, not in spec)",
                severity="minor",
            ))

        for g in removed:
            report.findings.append(DriftFinding(
                category="guardrail",
                description=f"Removed guardrail: {g} (in spec, not at runtime)",
                severity="significant",
            ))

    def _check_content_drift(
        self, spec_dir: Path, runtime_dir: Path, report: DriftReport
    ) -> None:
        """Check for significant content changes in shared files."""
        spec_files = self._collect_files(spec_dir)
        runtime_files = self._collect_files(runtime_dir)

        for rel_path in set(spec_files.keys()) & set(runtime_files.keys()):
            spec_content = spec_files[rel_path]
            runtime_content = runtime_files[rel_path]

            if spec_content != runtime_content:
                # Compute rough change percentage
                spec_lines = spec_content.splitlines()
                runtime_lines = runtime_content.splitlines()
                matcher = _SequenceMatcher(spec_lines, runtime_lines)
                ratio = matcher.ratio()
                change_pct = int((1 - ratio) * 100)

                if change_pct > 0:
                    report.findings.append(DriftFinding(
                        category="content_drift",
                        description=f"Content changed: {rel_path} ({change_pct}% different)",
                        severity="significant" if change_pct > 20 else "minor",
                    ))

    def _collect_files(self, directory: Path) -> dict[str, str]:
        """Collect all text files in a directory as {relative_path: content}."""
        if not directory.exists():
            return {}
        files = {}
        for f in directory.rglob("*"):
            if f.is_file() and f.suffix in (".md", ".yaml", ".yml", ".json", ".txt"):
                rel = str(f.relative_to(directory))
                try:
                    files[rel] = f.read_text()
                except Exception:
                    pass
        return files

    def _extract_traits(self, directory: Path) -> dict[str, float]:
        """Extract personality traits from YAML or JSON files."""
        traits: dict[str, float] = {}

        # Try personality.json
        for pattern in ["*.personality.json", "personality.json"]:
            for f in directory.glob(pattern):
                try:
                    data = json.loads(f.read_text())
                    if "traits" in data:
                        traits.update(data["traits"])
                except Exception:
                    pass

        # Try identity YAML
        for f in directory.glob("*.yaml"):
            try:
                data = yaml.safe_load(f.read_text())
                if isinstance(data, dict) and "personality" in data:
                    personality = data["personality"]
                    if isinstance(personality, dict) and "traits" in personality:
                        traits.update(personality["traits"])
            except Exception:
                pass

        return traits

    def _extract_guardrails(self, directory: Path) -> set[str]:
        """Extract guardrail keywords from markdown files."""
        guardrails: set[str] = set()
        guardrail_pattern = re.compile(
            r"(?:never|always|must not|do not|don't|guardrail|boundary)\s+(.+)",
            re.IGNORECASE,
        )

        for f in directory.rglob("*.md"):
            try:
                text = f.read_text()
                for match in guardrail_pattern.finditer(text):
                    guardrail = match.group(1).strip().lower()[:80]
                    if guardrail:
                        guardrails.add(guardrail)
            except Exception:
                pass

        return guardrails


class _SequenceMatcher:
    """Simple line-level sequence comparison."""

    def __init__(self, a: list[str], b: list[str]):
        self.a = a
        self.b = b

    def ratio(self) -> float:
        """Quick similarity ratio between two line lists."""
        if not self.a and not self.b:
            return 1.0
        if not self.a or not self.b:
            return 0.0

        a_set = set(self.a)
        b_set = set(self.b)
        intersection = a_set & b_set
        union = a_set | b_set

        if not union:
            return 1.0
        return len(intersection) / len(union)
