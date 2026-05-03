"""Tests for ``agentforge market`` (Phase 1.0)."""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from agentforge.corpus import Corpus, JDEntry, JDFrontmatter, load_corpus
from agentforge.department.cluster import cluster_skills
from agentforge.drill import ingest as drill_ingest
from agentforge.market.gap import compute_gap, render_gap_markdown
from agentforge.market.trends import compute_trends, render_trends_markdown
from agentforge.models.extracted_skills import (
    ExtractedRole,
    ExtractedSkill,
    ExtractionResult,
    SkillCategory,
    SkillImportance,
    SkillProficiency,
)


JD_FIXTURE = Path(__file__).parent / "fixtures" / "jd-corpus" / "dev-team"
SKILL_FIXTURE = Path(__file__).parent / "fixtures" / "skill-corpus" / "dev-skills"


def _skill(name: str, importance=SkillImportance.REQUIRED, category=SkillCategory.HARD) -> ExtractedSkill:
    return ExtractedSkill(
        name=name,
        category=category,
        proficiency=SkillProficiency.ADVANCED,
        importance=importance,
        context=f"used for {name}",
    )


def _result(role_title: str, *skills: ExtractedSkill, domain: str = "software-engineering",
            seniority: str = "senior") -> ExtractionResult:
    return ExtractionResult(
        role=ExtractedRole(
            title=role_title,
            seniority=seniority,
            domain=domain,
            purpose=f"do {role_title} work",
        ),
        skills=list(skills),
    )


# ---------- trends ----------


def test_trends_computes_top_skills_and_breakdowns():
    corpus = load_corpus(JD_FIXTURE)
    extractions = {
        e.role_id: _result(
            e.frontmatter.title,
            _skill("Python"),
            _skill("Postgres", importance=SkillImportance.PREFERRED),
            _skill(f"{e.role_id}-only"),
        )
        for e in corpus
    }
    report = compute_trends(corpus, extractions)

    assert report.role_count == 5
    assert len(report.skills) >= 6  # 2 shared + 5 role-only
    # Python should be the top skill (5/5 roles).
    py = next((s for s in report.skills if s.canonical_name == "Python"), None)
    assert py is not None and py.role_count == 5
    assert py.role_share == 1.0
    # Domain breakdown should reflect the corpus.
    assert report.domains.counts.get("software-engineering") == 5
    # Categories breakdown is non-empty.
    assert sum(report.categories.counts.values()) > 0


def test_trends_recency_skipped_when_buckets_too_small():
    """Dev-team fixture has 5 JDs all dated 2026-05-02 — too few on either
    side of any cutoff, so recency returns a note (not None) when at least
    some are dated, telling the caller why."""
    corpus = load_corpus(JD_FIXTURE)
    extractions = {e.role_id: _result(e.frontmatter.title, _skill("Python")) for e in corpus}
    report = compute_trends(
        corpus, extractions,
        recency_window_days=90,
        today=date(2026, 5, 3),  # 1 day after the JD dates
    )
    # All JDs are within the window, so prior bucket is empty → too-few-jds note.
    assert report.recency is not None
    assert report.recency.note is not None
    assert "too few datable JDs" in report.recency.note


def test_trends_recency_emits_rising_when_buckets_balanced(tmp_path):
    """Hand-craft a corpus that splits cleanly across the recency window."""
    # 3 recent JDs all featuring "Rust", 3 prior JDs all featuring "Perl".
    for i, (slug, posted, skill) in enumerate([
        ("alpha-recent", "2026-04-01", "Rust"),
        ("beta-recent", "2026-04-15", "Rust"),
        ("gamma-recent", "2026-04-25", "Rust"),
        ("delta-prior", "2025-08-01", "Perl"),
        ("epsilon-prior", "2025-09-01", "Perl"),
        ("zeta-prior", "2025-10-01", "Perl"),
    ]):
        (tmp_path / f"{slug}.md").write_text(
            f"---\ntitle: {slug.title()}\ndate: {posted}\n---\n\nbody.\n",
            encoding="utf-8",
        )
    corpus = load_corpus(tmp_path)
    assert len(corpus) == 6
    extractions: dict[str, ExtractionResult] = {}
    for entry in corpus:
        skill = "Rust" if "recent" in entry.role_id else "Perl"
        extractions[entry.role_id] = _result(entry.frontmatter.title, _skill(skill))

    report = compute_trends(
        corpus, extractions,
        recency_window_days=180,
        today=date(2026, 5, 1),
    )
    assert report.recency is not None
    assert report.recency.note is None  # buckets large enough
    assert "Rust" in report.recency.rising
    assert "Perl" in report.recency.falling


def test_render_trends_markdown_includes_top_skills_and_breakdowns():
    corpus = load_corpus(JD_FIXTURE)
    extractions = {
        e.role_id: _result(e.frontmatter.title, _skill("Python"), _skill("Postgres"))
        for e in corpus
    }
    report = compute_trends(corpus, extractions)
    md = render_trends_markdown(report, top_n=10)
    assert "market trends" in md
    assert "Top skills by demand" in md
    assert "Python" in md
    assert "Category breakdown" in md
    assert "Role mix" in md


# ---------- gap ----------


def test_gap_flags_market_only_skills():
    """Market demands Python+Postgres+Code Review; agent has neither cleanly,
    so all three should land in market_only with high severity."""
    corpus = load_corpus(JD_FIXTURE)
    # Each role demands Python + Postgres + Code Review (each 5/5 = required).
    extractions = {
        e.role_id: _result(
            e.frontmatter.title,
            _skill("Python", importance=SkillImportance.REQUIRED),
            _skill("Postgres", importance=SkillImportance.REQUIRED),
            _skill("Code Review", importance=SkillImportance.REQUIRED),
        )
        for e in corpus
    }
    landscape = cluster_skills(extractions)
    inventory = drill_ingest.ingest(SKILL_FIXTURE)
    report = compute_gap(landscape, inventory, corpus_root=str(JD_FIXTURE))

    market_only_names = {g.canonical_name for g in report.market_only}
    assert "Python" in market_only_names
    assert "Postgres" in market_only_names
    # Required + 5 roles → critical severity.
    py = next(g for g in report.market_only if g.canonical_name == "Python")
    assert py.severity == "critical"
    assert py.role_count == 5
    # Coverage score should be 0 (no load-bearing market skill is covered).
    assert report.coverage_score == 0.0


def test_gap_flags_shared_skills_when_agent_matches():
    """Make the market demand `ship-pr` (a slug from our skill fixture);
    the agent has a folder named ship-pr → that skill should land in shared."""
    extractions = {
        "alpha": _result("Alpha", _skill("ship-pr"), _skill("Postgres")),
        "beta":  _result("Beta",  _skill("ship-pr"), _skill("Postgres")),
        "gamma": _result("Gamma", _skill("ship-pr")),
    }
    landscape = cluster_skills(extractions)
    inventory = drill_ingest.ingest(SKILL_FIXTURE)
    report = compute_gap(landscape, inventory, corpus_root="(synthetic)")

    shared_names = {g.canonical_name for g in report.shared}
    assert "ship-pr" in shared_names
    s = next(g for g in report.shared if g.canonical_name == "ship-pr")
    assert "ship-pr" in s.in_agent_skills
    assert s.role_count == 3


def test_gap_flags_agent_only_skills():
    """Build a market that only demands skills the agent doesn't have; the
    agent's other skill folders should appear in agent_only."""
    extractions = {
        "alpha": _result("Alpha", _skill("Postgres")),
        "beta":  _result("Beta",  _skill("Postgres")),
    }
    landscape = cluster_skills(extractions)
    inventory = drill_ingest.ingest(SKILL_FIXTURE)
    report = compute_gap(landscape, inventory, corpus_root="(synthetic)")

    agent_only_names = {g.canonical_name for g in report.agent_only}
    # `run-tests` is a fixture skill; its slug shouldn't substring-match Postgres.
    assert "run tests" in agent_only_names
    # `decommissioned` has no SKILL.md, so it shouldn't appear at all.
    assert not any("decommissioned" in n for n in agent_only_names)


def test_gap_coverage_score_full_when_agent_covers_load_bearing():
    """If every cluster appearing in ≥2 roles is covered by the agent,
    coverage should be 100%."""
    extractions = {
        "alpha": _result("Alpha", _skill("ship-pr")),
        "beta":  _result("Beta",  _skill("ship-pr")),
        "gamma": _result("Gamma", _skill("ship-pr")),
    }
    landscape = cluster_skills(extractions)
    inventory = drill_ingest.ingest(SKILL_FIXTURE)
    report = compute_gap(landscape, inventory, corpus_root="(synthetic)")
    assert report.coverage_score == 1.0


def test_gap_coverage_score_empty_landscape_is_full():
    extractions: dict = {}
    landscape = cluster_skills(extractions)
    inventory = drill_ingest.ingest(SKILL_FIXTURE)
    report = compute_gap(landscape, inventory)
    assert report.coverage_score == 1.0
    assert any("trivially" in n for n in report.notes)


def test_render_gap_markdown_includes_coverage_and_kinds():
    extractions = {
        "alpha": _result("Alpha",
                         _skill("Python", importance=SkillImportance.REQUIRED)),
        "beta": _result("Beta",
                        _skill("Python", importance=SkillImportance.REQUIRED)),
    }
    landscape = cluster_skills(extractions)
    inventory = drill_ingest.ingest(SKILL_FIXTURE)
    report = compute_gap(landscape, inventory, corpus_root="(synthetic)")
    md = render_gap_markdown(report)
    assert "market gap" in md
    assert "Coverage:" in md
    assert "## market_only" in md
    assert "Python" in md
