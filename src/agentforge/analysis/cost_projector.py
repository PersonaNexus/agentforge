"""Cost projection: estimate token costs for a specific generated SKILL.md file."""

from __future__ import annotations

from pydantic import BaseModel, Field

from agentforge.analysis.prompt_size_analyzer import _estimate_tokens

# Re-export constants from value_estimator for consistent cost modelling
_DEFAULT_COST_PER_1K_TOKENS = 0.008
_DEFAULT_MONTHLY_INFRA = 200.0
_WORKING_DAYS_PER_MONTH = 22

# Average completion tokens per invocation (response side), by estimated
# prompt complexity.  We use a simple heuristic: larger prompts tend to
# produce longer completions.
_BASE_COMPLETION_TOKENS = 600
_COMPLETION_SCALING = 0.3  # completion ≈ base + prompt_tokens × scaling


class CostProjection(BaseModel):
    """Projected token costs for running a skill."""

    prompt_tokens: int = Field(..., description="System prompt size in tokens")
    estimated_completion_tokens: int = Field(
        ..., description="Avg completion tokens per call"
    )
    tokens_per_call: int = Field(
        ..., description="prompt_tokens + completion tokens"
    )
    estimated_daily_calls: int
    monthly_token_usage: int
    monthly_cost_usd: float
    annual_cost_usd: float
    cost_per_call_usd: float
    budget_utilization: float = Field(
        ..., description="Fraction of monthly budget consumed (0-1)"
    )


class CostProjector:
    """Project token costs from a SKILL.md file's actual size.

    Unlike ``ValueEstimator`` which works at the role/extraction level,
    this class operates on the *generated* prompt content so the
    projection reflects the real system-prompt cost per invocation.
    """

    def __init__(
        self,
        cost_per_1k: float = _DEFAULT_COST_PER_1K_TOKENS,
        monthly_budget: float = 500.0,
    ) -> None:
        self.cost_per_1k = cost_per_1k
        self.monthly_budget = monthly_budget

    def project(
        self,
        skill_md: str,
        daily_calls: int = 50,
    ) -> CostProjection:
        """Project costs for a skill file.

        Args:
            skill_md: The SKILL.md content (system prompt).
            daily_calls: Expected invocations per working day.
        """
        prompt_tokens = _estimate_tokens(skill_md)
        completion_tokens = int(
            _BASE_COMPLETION_TOKENS + prompt_tokens * _COMPLETION_SCALING
        )
        tokens_per_call = prompt_tokens + completion_tokens

        monthly_calls = daily_calls * _WORKING_DAYS_PER_MONTH
        monthly_tokens = tokens_per_call * monthly_calls

        monthly_cost = (monthly_tokens / 1000) * self.cost_per_1k
        annual_cost = monthly_cost * 12
        cost_per_call = (tokens_per_call / 1000) * self.cost_per_1k

        budget_util = monthly_cost / self.monthly_budget if self.monthly_budget > 0 else 0.0

        return CostProjection(
            prompt_tokens=prompt_tokens,
            estimated_completion_tokens=completion_tokens,
            tokens_per_call=tokens_per_call,
            estimated_daily_calls=daily_calls,
            monthly_token_usage=monthly_tokens,
            monthly_cost_usd=round(monthly_cost, 2),
            annual_cost_usd=round(annual_cost, 2),
            cost_per_call_usd=round(cost_per_call, 6),
            budget_utilization=round(budget_util, 4),
        )
