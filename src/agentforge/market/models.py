"""Pydantic models for ``agentforge market`` reports."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class SkillTrend(BaseModel):
    """One skill in the market, summarized across the corpus."""

    canonical_name: str
    role_count: int  # how many roles in the corpus mention it
    role_share: float  # role_count / total_roles
    role_ids: list[str] = Field(default_factory=list)
    category: str | None = None
    importance_max: str | None = None
    importance_distribution: dict[str, int] = Field(default_factory=dict)


class CategoryBreakdown(BaseModel):
    """Counts of unique skills by category — high-level corpus shape."""

    counts: dict[str, int] = Field(default_factory=dict)


class DomainBreakdown(BaseModel):
    """Counts of roles by ``role.domain``."""

    counts: dict[str, int] = Field(default_factory=dict)


class SeniorityBreakdown(BaseModel):
    """Counts of roles by ``role.seniority``."""

    counts: dict[str, int] = Field(default_factory=dict)


class RecencyBucket(BaseModel):
    """One side of the recency split — recent vs prior window."""

    label: str  # "recent" | "prior"
    role_ids: list[str] = Field(default_factory=list)
    skill_counts: dict[str, int] = Field(default_factory=dict)  # canonical_name → role_count


class RecencySignal(BaseModel):
    """Skills rising / falling between a recent window and a prior window.

    Empty when the corpus has no datable JDs or fewer than 2 roles per side.
    """

    schema_version: str = "1"
    window_days: int = 0
    recent: RecencyBucket = Field(default_factory=lambda: RecencyBucket(label="recent"))
    prior: RecencyBucket = Field(default_factory=lambda: RecencyBucket(label="prior"))
    rising: list[str] = Field(default_factory=list)  # canonical_name list
    falling: list[str] = Field(default_factory=list)
    note: str | None = None


class TrendsReport(BaseModel):
    """Output of ``market trends``."""

    schema_version: str = "1"
    corpus_root: str
    generated_at: datetime
    role_count: int
    role_ids: list[str] = Field(default_factory=list)
    skills: list[SkillTrend] = Field(default_factory=list)  # sorted by role_count desc
    categories: CategoryBreakdown = Field(default_factory=CategoryBreakdown)
    domains: DomainBreakdown = Field(default_factory=DomainBreakdown)
    seniority: SeniorityBreakdown = Field(default_factory=SeniorityBreakdown)
    recency: RecencySignal | None = None
    notes: list[str] = Field(default_factory=list)
