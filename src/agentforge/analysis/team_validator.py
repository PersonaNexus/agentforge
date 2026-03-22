"""Team relationship validation — catch overlaps and routing conflicts at build time.

Validates an orchestration configuration against PersonaNexus's relationship
schema before deployment. Surfaces:
  - Trait overlap percentages between agents
  - Missing conductor deference declarations
  - Guardrail coverage gaps
  - Routing conflicts
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agentforge.composition.models import ForgedTeam, ForgedTeammate


@dataclass
class ValidationIssue:
    """A single validation finding."""

    severity: str  # "error", "warning", "info"
    category: str  # "overlap", "routing", "guardrail", "relationship"
    message: str
    agents: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        icon = {"error": "✗", "warning": "⚠", "info": "✓"}.get(self.severity, "?")
        return f"{icon} {self.message}"


@dataclass
class ValidationReport:
    """Complete team validation report."""

    issues: list[ValidationIssue] = field(default_factory=list)
    trait_overlaps: dict[str, float] = field(default_factory=dict)  # "A+B" -> pct
    guardrail_coverage: dict[str, bool] = field(default_factory=dict)
    passed: bool = True

    @property
    def errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == "warning"]

    def summary(self) -> str:
        e = len(self.errors)
        w = len(self.warnings)
        status = "PASS" if self.passed else "FAIL"
        return f"{status}: {e} error(s), {w} warning(s)"


class TeamValidator:
    """Validates team composition for overlaps, gaps, and conflicts."""

    OVERLAP_THRESHOLD = 0.6  # 60% overlap triggers a warning

    def validate(self, team: ForgedTeam) -> ValidationReport:
        """Run full validation on a forged team."""
        report = ValidationReport()

        self._check_trait_overlaps(team, report)
        self._check_conductor_deference(team, report)
        self._check_guardrail_coverage(team, report)
        self._check_routing_gaps(team, report)
        self._check_skill_duplication(team, report)

        report.passed = len(report.errors) == 0
        return report

    def _check_trait_overlaps(
        self, team: ForgedTeam, report: ValidationReport
    ) -> None:
        """Check for high trait overlap between agent pairs."""
        teammates = team.teammates
        for i, a in enumerate(teammates):
            for b in teammates[i + 1:]:
                overlap = self._compute_trait_overlap(a, b)
                key = f"{a.teammate.name}+{b.teammate.name}"
                report.trait_overlaps[key] = overlap

                if overlap >= self.OVERLAP_THRESHOLD:
                    pct = int(overlap * 100)
                    report.issues.append(ValidationIssue(
                        severity="warning",
                        category="overlap",
                        message=(
                            f"{a.teammate.name} + {b.teammate.name}: "
                            f"{pct}% trait overlap — consider merging or differentiating"
                        ),
                        agents=[a.teammate.name, b.teammate.name],
                    ))

    def _compute_trait_overlap(
        self, a: ForgedTeammate, b: ForgedTeammate
    ) -> float:
        """Compute trait overlap percentage between two agents."""
        a_traits = a.teammate.personality
        b_traits = b.teammate.personality

        if not a_traits or not b_traits:
            return 0.0

        all_keys = set(a_traits.keys()) | set(b_traits.keys())
        if not all_keys:
            return 0.0

        # Overlap = 1 - average absolute difference
        total_diff = 0.0
        for key in all_keys:
            a_val = a_traits.get(key, 0.5)
            b_val = b_traits.get(key, 0.5)
            total_diff += abs(a_val - b_val)

        avg_diff = total_diff / len(all_keys)
        return round(1.0 - avg_diff, 2)

    def _check_conductor_deference(
        self, team: ForgedTeam, report: ValidationReport
    ) -> None:
        """Check that at least one agent defers to the conductor."""
        conductor_name = team.conductor.skill_name
        has_deference = False

        # Check routing table and handoffs for conductor references
        for handoff in team.conductor.handoffs:
            if handoff.to_agent == conductor_name or handoff.from_agent == conductor_name:
                has_deference = True
                break

        if not has_deference and len(team.teammates) > 1:
            report.issues.append(ValidationIssue(
                severity="warning",
                category="relationship",
                message=(
                    "No agent has explicit defers_to conductor — "
                    "conductor may be ignored in routing"
                ),
            ))

    def _check_guardrail_coverage(
        self, team: ForgedTeam, report: ValidationReport
    ) -> None:
        """Check that all agents have basic guardrails."""
        essential_guardrails = ["no_fabrication", "domain_boundary"]

        for ft in team.teammates:
            agent_name = ft.teammate.name
            skill_md = ft.skill_folder.skill_md.lower()

            has_no_fabrication = any(
                kw in skill_md
                for kw in ["no fabricat", "never fabricat", "no_fabrication", "don't fabricat"]
            )
            has_domain = any(
                kw in skill_md
                for kw in ["domain expert", "stay within", "domain_boundary", "outside"]
            )

            report.guardrail_coverage[f"{agent_name}:no_fabrication"] = has_no_fabrication
            report.guardrail_coverage[f"{agent_name}:domain_boundary"] = has_domain

            if not has_no_fabrication:
                report.issues.append(ValidationIssue(
                    severity="warning",
                    category="guardrail",
                    message=f"{agent_name}: missing no_fabrication guardrail",
                    agents=[agent_name],
                ))

        # Summary
        all_covered = all(report.guardrail_coverage.values())
        if all_covered:
            report.issues.append(ValidationIssue(
                severity="info",
                category="guardrail",
                message="Guardrail coverage: all agents have essential guardrails",
            ))

    def _check_routing_gaps(
        self, team: ForgedTeam, report: ValidationReport
    ) -> None:
        """Check for routing table gaps."""
        routing = team.conductor.routing_table
        agent_names = {ft.teammate.name for ft in team.teammates}
        routed_agents = set(routing.keys())

        unrouted = agent_names - routed_agents
        for name in unrouted:
            report.issues.append(ValidationIssue(
                severity="warning",
                category="routing",
                message=f"{name}: not in conductor routing table — may never receive tasks",
                agents=[name],
            ))

    def _check_skill_duplication(
        self, team: ForgedTeam, report: ValidationReport
    ) -> None:
        """Check for duplicated skills across agents."""
        skill_owners: dict[str, list[str]] = {}

        for ft in team.teammates:
            for skill in ft.teammate.skills:
                name = skill.name
                if name not in skill_owners:
                    skill_owners[name] = []
                skill_owners[name].append(ft.teammate.name)

        for skill_name, owners in skill_owners.items():
            if len(owners) > 1:
                report.issues.append(ValidationIssue(
                    severity="warning",
                    category="overlap",
                    message=(
                        f"Skill '{skill_name}' assigned to multiple agents: "
                        f"{', '.join(owners)} — consider consolidating"
                    ),
                    agents=owners,
                ))
