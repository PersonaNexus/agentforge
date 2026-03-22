"""Evaluate skill test results using LLM-as-judge."""
from __future__ import annotations
import json
from pydantic import BaseModel, Field
from agentforge.testing.models import (
    CriterionScore,
    ScoredExecution,
    TestExecution,
    TestReport,
)


class _JudgeVerdict(BaseModel):
    """LLM judge output for a single criterion."""
    score: float = Field(..., ge=0.0, le=1.0)
    rationale: str = ""


class Evaluator:
    """Score test executions against quality criteria using LLM-as-judge."""

    def evaluate(
        self,
        executions: list[TestExecution],
        default_criteria: list[str] | None = None,
        llm_client: object | None = None,
    ) -> TestReport:
        """Evaluate all test executions and produce a report."""
        fallback_criteria = default_criteria or [
            "Response is relevant to the request",
            "Response demonstrates domain expertise",
            "Response is well-structured and clear",
        ]

        scored = []
        for execution in executions:
            criteria = execution.scenario.quality_criteria or fallback_criteria
            if llm_client:
                criterion_scores = self._judge_with_llm(execution, criteria, llm_client)
            else:
                criterion_scores = self._judge_heuristic(execution, criteria)

            overall = (
                sum(c.score for c in criterion_scores) / len(criterion_scores)
                if criterion_scores
                else 0.0
            )

            scored.append(ScoredExecution(
                execution=execution,
                criterion_scores=criterion_scores,
                overall_score=round(overall, 3),
            ))

        return self._build_report(scored)

    def _judge_with_llm(
        self,
        execution: TestExecution,
        criteria: list[str],
        llm_client: object,
    ) -> list[CriterionScore]:
        """Use LLM to judge response against criteria."""
        scores = []
        for criterion in criteria:
            prompt = (
                f"You are evaluating an AI agent's response quality.\n\n"
                f"## Quality Criterion\n{criterion}\n\n"
                f"## User Request\n{execution.scenario.input_prompt}\n\n"
                f"## Agent Response\n{execution.response[:3000]}\n\n"
                f"Score 0.0-1.0 on how well the response meets this criterion.\n"
                f"- 0.0: Completely fails the criterion\n"
                f"- 0.5: Partially meets, significant gaps\n"
                f"- 1.0: Fully satisfies the criterion"
            )
            try:
                verdict = llm_client.extract_structured(
                    prompt=prompt,
                    output_schema=_JudgeVerdict,
                    max_tokens=256,
                )
                scores.append(CriterionScore(
                    criterion=criterion,
                    score=verdict.score,
                    rationale=verdict.rationale,
                ))
            except Exception:
                scores.append(CriterionScore(
                    criterion=criterion,
                    score=0.5,
                    rationale="Evaluation failed, using default score",
                ))
        return scores

    def _judge_heuristic(
        self,
        execution: TestExecution,
        criteria: list[str],
    ) -> list[CriterionScore]:
        """Simple heuristic scoring when no LLM is available."""
        scores = []
        response = execution.response
        for criterion in criteria:
            score = 0.5  # baseline
            # Length check: longer responses tend to be more thorough
            if len(response) > 500:
                score += 0.1
            if len(response) > 1000:
                score += 0.1
            # Check if response mentions key terms from the criterion
            criterion_words = set(criterion.lower().split())
            response_words = set(response.lower().split())
            overlap = len(criterion_words & response_words) / max(len(criterion_words), 1)
            score += overlap * 0.2
            score = min(1.0, max(0.0, score))
            scores.append(CriterionScore(
                criterion=criterion,
                score=round(score, 3),
                rationale="Heuristic evaluation (no LLM judge available)",
            ))
        return scores

    def _build_report(self, scored: list[ScoredExecution]) -> TestReport:
        """Build a test report from scored executions."""
        if not scored:
            return TestReport()

        overall = sum(s.overall_score for s in scored) / len(scored)

        # Find weakest criteria
        criterion_totals: dict[str, list[float]] = {}
        for s in scored:
            for cs in s.criterion_scores:
                criterion_totals.setdefault(cs.criterion, []).append(cs.score)

        criterion_avgs = {
            c: sum(scores) / len(scores) for c, scores in criterion_totals.items()
        }
        weakest = sorted(criterion_avgs.items(), key=lambda x: x[1])
        weakest_criteria = [c for c, _ in weakest[:3] if criterion_avgs[c] < 0.7]

        # Generate recommendations
        recommendations = []
        for criterion, avg in weakest[:3]:
            if avg < 0.5:
                recommendations.append(
                    f"Critical: '{criterion}' scored {avg:.0%} — add methodology for this area"
                )
            elif avg < 0.7:
                recommendations.append(
                    f"Improve: '{criterion}' scored {avg:.0%} — consider adding examples or templates"
                )

        return TestReport(
            scored_executions=scored,
            overall_score=round(overall, 3),
            weakest_criteria=weakest_criteria,
            recommendations=recommendations,
        )
