"""Supplement quality scoring — score supplementary sources before ingestion.

Scores each supplement source on:
  - Signal density: ratio of actionable content to noise
  - Role relevance: how well the content matches the role description
  - Recency: freshness indicators in the content

Surfaces a quality report and flags low-quality sources.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class SupplementScore:
    """Quality score for a single supplement source."""

    source: str
    signal_density: float = 0.0  # 0-1
    role_relevance: float = 0.0  # 0-1
    recency_score: float = 0.0  # 0-1
    overall_score: float = 0.0  # 0-1
    assessment: str = ""  # "high", "medium", "low"

    @property
    def pct(self) -> int:
        return int(self.overall_score * 100)

    def __str__(self) -> str:
        return f"{self.source}    {self.pct}% signal ({self.assessment})"


@dataclass
class SupplementReport:
    """Quality report for all supplement sources."""

    scores: list[SupplementScore] = field(default_factory=list)
    threshold: float = 0.4

    @property
    def low_quality_sources(self) -> list[SupplementScore]:
        return [s for s in self.scores if s.overall_score < self.threshold]

    @property
    def has_low_quality(self) -> bool:
        return len(self.low_quality_sources) > 0


class SupplementScorer:
    """Scores supplement sources on signal quality before ingestion."""

    # Noise indicators — content that dilutes signal
    NOISE_PATTERNS = [
        r"^(hi|hey|hello|thanks|thank you|ok|okay|sure|np|no problem)\b",
        r"^(lol|haha|heh|wow|nice|cool|great)\b",
        r"^\W*$",  # empty or whitespace-only lines
        r"^(sent from|--\s*$|_{3,})",  # signatures/separators
        r"^>",  # quoted text in emails/chats
    ]

    # Signal indicators — actionable content
    SIGNAL_PATTERNS = [
        r"\b(when|if|should|must|always|never|ensure|verify)\b",
        r"\b(step \d|first|second|third|then|next|finally)\b",
        r"\b(process|workflow|procedure|framework|methodology)\b",
        r"\b(decision|criteria|requirement|standard|metric)\b",
        r"\b(example|template|format|output|deliverable)\b",
    ]

    # Recency patterns
    RECENCY_PATTERNS = [
        r"\b20(2[4-6])\b",  # recent years
        r"\b(today|yesterday|this week|this month|recently|latest)\b",
        r"\b(Q[1-4]\s*20\d{2})\b",  # quarterly references
    ]

    def score_text(
        self,
        text: str,
        source_name: str,
        role_keywords: list[str] | None = None,
    ) -> SupplementScore:
        """Score a text supplement on signal quality."""
        lines = text.strip().split("\n")
        if not lines:
            return SupplementScore(source=source_name, assessment="low")

        signal_density = self._compute_signal_density(lines)
        role_relevance = self._compute_role_relevance(text, role_keywords or [])
        recency = self._compute_recency(text)

        overall = (signal_density * 0.5) + (role_relevance * 0.35) + (recency * 0.15)

        if overall >= 0.65:
            assessment = "high"
        elif overall >= 0.4:
            assessment = "medium"
        else:
            assessment = "low"

        return SupplementScore(
            source=source_name,
            signal_density=round(signal_density, 2),
            role_relevance=round(role_relevance, 2),
            recency_score=round(recency, 2),
            overall_score=round(overall, 2),
            assessment=assessment,
        )

    def score_file(
        self,
        path: Path,
        role_keywords: list[str] | None = None,
    ) -> SupplementScore:
        """Score a file supplement on signal quality."""
        text = path.read_text()
        return self.score_text(text, path.name, role_keywords)

    def score_sources(
        self,
        sources: list[tuple[str, str]],  # (name, text) pairs
        role_keywords: list[str] | None = None,
    ) -> SupplementReport:
        """Score multiple sources and produce a report."""
        report = SupplementReport()
        for name, text in sources:
            score = self.score_text(text, name, role_keywords)
            report.scores.append(score)
        return report

    def _compute_signal_density(self, lines: list[str]) -> float:
        """Ratio of signal lines to total lines."""
        if not lines:
            return 0.0

        signal_count = 0
        noise_count = 0

        for line in lines:
            stripped = line.strip().lower()
            if not stripped:
                noise_count += 1
                continue

            is_noise = any(
                re.search(pat, stripped, re.IGNORECASE)
                for pat in self.NOISE_PATTERNS
            )
            is_signal = any(
                re.search(pat, stripped, re.IGNORECASE)
                for pat in self.SIGNAL_PATTERNS
            )

            if is_noise and not is_signal:
                noise_count += 1
            elif is_signal:
                signal_count += 1

        total = len(lines)
        if total == 0:
            return 0.0

        # Signal density = weighted: signal lines boost, noise lines reduce
        return min(1.0, (signal_count * 2) / max(total, 1))

    def _compute_role_relevance(
        self, text: str, keywords: list[str]
    ) -> float:
        """Proportion of role keywords found in text."""
        if not keywords:
            return 0.5  # neutral if no keywords provided

        text_lower = text.lower()
        matches = sum(1 for kw in keywords if kw.lower() in text_lower)
        return min(1.0, matches / max(len(keywords), 1))

    def _compute_recency(self, text: str) -> float:
        """Score based on presence of recency indicators."""
        matches = sum(
            1 for pat in self.RECENCY_PATTERNS
            if re.search(pat, text, re.IGNORECASE)
        )
        return min(1.0, matches * 0.35)
