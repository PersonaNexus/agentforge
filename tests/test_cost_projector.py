"""Tests for cost projector."""

from __future__ import annotations

import pytest

from agentforge.analysis.cost_projector import CostProjection, CostProjector
from agentforge.generation.skill_file import SkillFileGenerator
from tests.conftest import _make_sample_extraction


def _make_skill_md() -> str:
    return SkillFileGenerator().generate(_make_sample_extraction())


class TestCostProjection:
    def test_basic_projection(self):
        projector = CostProjector()
        report = projector.project("a" * 4000, daily_calls=50)
        assert report.prompt_tokens == 1000
        assert report.tokens_per_call > report.prompt_tokens
        assert report.monthly_token_usage > 0
        assert report.monthly_cost_usd > 0
        assert report.annual_cost_usd == round(report.monthly_cost_usd * 12, 2)

    def test_realistic_skill_md(self):
        skill_md = _make_skill_md()
        projector = CostProjector()
        report = projector.project(skill_md)
        # Realistic skill is ~1-3K tokens, costs should be modest
        assert report.prompt_tokens > 100
        assert report.monthly_cost_usd > 0
        assert report.annual_cost_usd > 0

    def test_empty_prompt(self):
        projector = CostProjector()
        report = projector.project("", daily_calls=10)
        assert report.prompt_tokens == 0
        # Still has completion tokens
        assert report.tokens_per_call > 0

    def test_daily_calls_scales_cost(self):
        projector = CostProjector()
        low = projector.project("test content", daily_calls=10)
        high = projector.project("test content", daily_calls=100)
        assert high.monthly_cost_usd > low.monthly_cost_usd
        assert high.monthly_token_usage > low.monthly_token_usage

    def test_cost_per_1k_override(self):
        cheap = CostProjector(cost_per_1k=0.001)
        expensive = CostProjector(cost_per_1k=0.050)
        cheap_report = cheap.project("a" * 4000, daily_calls=50)
        expensive_report = expensive.project("a" * 4000, daily_calls=50)
        assert expensive_report.monthly_cost_usd > cheap_report.monthly_cost_usd

    def test_budget_utilization(self):
        projector = CostProjector(monthly_budget=100.0)
        report = projector.project("a" * 4000, daily_calls=50)
        assert 0 <= report.budget_utilization
        expected = report.monthly_cost_usd / 100.0
        assert abs(report.budget_utilization - expected) < 0.01

    def test_cost_per_call(self):
        projector = CostProjector()
        report = projector.project("a" * 4000, daily_calls=50)
        expected = (report.tokens_per_call / 1000) * 0.008
        assert abs(report.cost_per_call_usd - expected) < 0.0001

    def test_completion_tokens_scale_with_prompt(self):
        projector = CostProjector()
        small = projector.project("a" * 400)
        large = projector.project("a" * 40000)
        assert large.estimated_completion_tokens > small.estimated_completion_tokens

    def test_tokens_per_call_is_sum(self):
        projector = CostProjector()
        report = projector.project("a" * 4000)
        assert report.tokens_per_call == report.prompt_tokens + report.estimated_completion_tokens
