"""Data models for skill testing and validation."""
from __future__ import annotations
from dataclasses import dataclass, field
from pydantic import BaseModel, Field

@dataclass
class TestScenario:
    """A single test case for validating a skill."""
    name: str
    input_prompt: str
    expected_technique: str = ""
    expected_format: str = ""
    quality_criteria: list[str] = field(default_factory=list)
    source: str = "trigger"  # trigger, responsibility, edge_case

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "input_prompt": self.input_prompt,
            "expected_technique": self.expected_technique,
            "expected_format": self.expected_format,
            "quality_criteria": self.quality_criteria,
            "source": self.source,
        }

@dataclass
class TestExecution:
    """Result of running a single test scenario."""
    scenario: TestScenario
    response: str
    tokens_used: int = 0
    latency_ms: float = 0.0

    def to_dict(self) -> dict:
        return {
            "scenario": self.scenario.to_dict(),
            "response": self.response,
            "tokens_used": self.tokens_used,
            "latency_ms": self.latency_ms,
        }

@dataclass
class CriterionScore:
    """Score for a single quality criterion."""
    criterion: str
    score: float  # 0.0 - 1.0
    rationale: str = ""

    def to_dict(self) -> dict:
        return {
            "criterion": self.criterion,
            "score": self.score,
            "rationale": self.rationale,
        }

@dataclass
class ScoredExecution:
    """A test execution with quality scores."""
    execution: TestExecution
    criterion_scores: list[CriterionScore] = field(default_factory=list)
    overall_score: float = 0.0

    def to_dict(self) -> dict:
        return {
            "execution": self.execution.to_dict(),
            "criterion_scores": [c.to_dict() for c in self.criterion_scores],
            "overall_score": self.overall_score,
        }

@dataclass
class TestReport:
    """Complete test report for a skill."""
    scored_executions: list[ScoredExecution] = field(default_factory=list)
    overall_score: float = 0.0
    weakest_criteria: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    pass_threshold: float = 0.7

    @property
    def pass_rate(self) -> float:
        if not self.scored_executions:
            return 0.0
        passed = sum(1 for e in self.scored_executions if e.overall_score >= self.pass_threshold)
        return passed / len(self.scored_executions)

    def summary(self) -> str:
        total = len(self.scored_executions)
        passed = sum(1 for e in self.scored_executions if e.overall_score >= self.pass_threshold)
        pct = int(self.pass_rate * 100)
        weak = f" Weakest: {', '.join(self.weakest_criteria[:2])}" if self.weakest_criteria else ""
        return f"{passed}/{total} scenarios passed ({pct}%).{weak}"

    def to_dict(self) -> dict:
        return {
            "scored_executions": [s.to_dict() for s in self.scored_executions],
            "overall_score": self.overall_score,
            "weakest_criteria": self.weakest_criteria,
            "recommendations": self.recommendations,
            "pass_rate": self.pass_rate,
            "summary": self.summary(),
        }
