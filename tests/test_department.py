"""Tests for the corpus loader and department clustering."""

from __future__ import annotations

from pathlib import Path

import pytest

from agentforge.corpus import (
    Corpus,
    JDEntry,
    JDFrontmatter,
    load_corpus,
    parse_frontmatter,
)
from agentforge.department.cluster import cluster_skills
from agentforge.department.synthesize import (
    extract_corpus,
    render_report_markdown,
)
from agentforge.models.extracted_skills import (
    ExtractedRole,
    ExtractedSkill,
    ExtractionResult,
    SkillCategory,
    SkillImportance,
    SkillProficiency,
)


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "jd-corpus" / "dev-team"


# ---------- corpus loader ----------

def test_parse_frontmatter_extracts_yaml_and_body():
    text = "---\ntitle: Test Role\nseniority: senior\n---\n\n# Body\n\nBody content.\n"
    fm, body = parse_frontmatter(text)
    assert fm is not None
    assert fm.title == "Test Role"
    assert fm.seniority == "senior"
    assert "Body content." in body


def test_parse_frontmatter_missing_returns_none():
    fm, body = parse_frontmatter("# No frontmatter here\n\nJust body.\n")
    assert fm is None
    assert body.startswith("# No frontmatter here")


def test_parse_frontmatter_rejects_invalid_yaml():
    text = "---\n: : invalid : :\n---\n\nbody"
    with pytest.raises(ValueError):
        parse_frontmatter(text)


def test_jd_frontmatter_requires_title():
    with pytest.raises(ValueError):
        JDFrontmatter.model_validate({"seniority": "senior"})


def test_jd_frontmatter_accepts_date_alias():
    fm = JDFrontmatter.model_validate({"title": "x", "date": "2026-05-02"})
    assert fm.posted == "2026-05-02"


def test_jd_frontmatter_coerces_date_object():
    """YAML auto-parses unquoted ISO dates into datetime.date — must coerce."""
    from datetime import date
    fm = JDFrontmatter.model_validate({"title": "x", "date": date(2026, 5, 2)})
    assert fm.posted == "2026-05-02"


def test_load_corpus_dev_team_fixture():
    corpus = load_corpus(FIXTURE_ROOT)
    assert len(corpus) == 5
    role_ids = {e.role_id for e in corpus}
    assert role_ids == {
        "backend-engineer",
        "devops-engineer",
        "engineering-manager",
        "frontend-engineer",
        "qa-engineer",
    }
    em = corpus.by_role("engineering-manager")
    assert em is not None
    assert em.frontmatter.title == "Engineering Manager"
    assert em.frontmatter.seniority == "senior"


def test_load_corpus_missing_directory():
    with pytest.raises(FileNotFoundError):
        load_corpus(Path("/nonexistent/jd-corpus/path"))


def test_load_corpus_rejects_jd_without_frontmatter(tmp_path):
    (tmp_path / "rogue.md").write_text("# Just a heading\n\nNo frontmatter.\n")
    with pytest.raises(ValueError, match="missing YAML frontmatter"):
        load_corpus(tmp_path)


# ---------- skill clustering ----------

def _skill(name: str, category=SkillCategory.HARD,
           importance=SkillImportance.REQUIRED) -> ExtractedSkill:
    return ExtractedSkill(
        name=name,
        category=category,
        proficiency=SkillProficiency.ADVANCED,
        importance=importance,
        context="(test)",
    )


def _result(role_title: str, *skills: ExtractedSkill) -> ExtractionResult:
    return ExtractionResult(
        role=ExtractedRole(
            title=role_title, seniority="senior", domain="test",
            purpose="test", responsibilities=[],
        ),
        skills=list(skills),
    )


def test_cluster_skills_finds_overlap():
    extractions = {
        "alpha": _result("Alpha", _skill("Python"), _skill("Postgres"),
                         _skill("Alpha-only thing")),
        "beta": _result("Beta", _skill("Python"), _skill("Postgres"),
                        _skill("Beta-only thing")),
        "gamma": _result("Gamma", _skill("Python"), _skill("Gamma-only thing")),
    }
    landscape = cluster_skills(extractions)

    assert landscape.role_count == 3
    py = next((c for c in landscape.clusters if c.canonical_name == "Python"), None)
    assert py is not None
    assert py.role_count == 3
    assert set(py.role_ids) == {"alpha", "beta", "gamma"}

    pg = next((c for c in landscape.clusters if c.canonical_name == "Postgres"), None)
    assert pg is not None
    assert pg.role_count == 2

    # Role-specific
    a_only = next((c for c in landscape.clusters
                   if c.canonical_name == "Alpha-only thing"), None)
    assert a_only is not None
    assert a_only.role_count == 1
    assert not a_only.is_shared


def test_cluster_skills_normalizes_phrasing():
    """Aggressive normalization should fold 'PostgreSQL' and 'Postgres' together."""
    extractions = {
        "a": _result("A", _skill("PostgreSQL")),
        "b": _result("B", _skill("Postgres")),
    }
    landscape = cluster_skills(extractions)
    assert len(landscape.shared_clusters) == 1
    assert landscape.shared_clusters[0].role_count == 2
    assert len(landscape.shared_clusters[0].member_names) == 2  # both phrasings preserved


def test_cluster_skills_picks_max_importance():
    extractions = {
        "a": _result("A", _skill("X", importance=SkillImportance.NICE_TO_HAVE)),
        "b": _result("B", _skill("X", importance=SkillImportance.REQUIRED)),
    }
    landscape = cluster_skills(extractions)
    x = next(c for c in landscape.clusters if c.canonical_name == "X")
    assert x.importance_max == "required"


def test_extract_corpus_uses_cache(tmp_path):
    """Second extract_corpus call hits the cache and skips the extractor."""
    (tmp_path / "alpha.md").write_text(
        "---\ntitle: Alpha\n---\n\nbody alpha\n", encoding="utf-8",
    )
    corpus = load_corpus(tmp_path)
    calls = {"n": 0}

    def stub_extract(entry):
        calls["n"] += 1
        return _result(entry.title, _skill("Python"))

    extract_corpus(corpus, stub_extract)
    assert calls["n"] == 1
    extract_corpus(corpus, stub_extract)
    assert calls["n"] == 1  # second pass came from cache


def test_render_report_markdown_includes_shared_section():
    """Smoke render — confirms shape, role IDs, and shared/role-specific split."""
    extractions = {
        "alpha": _result("Alpha", _skill("Python"), _skill("Alpha-only")),
        "beta": _result("Beta", _skill("Python"), _skill("Beta-only")),
    }
    landscape = cluster_skills(extractions)
    corpus = Corpus(root="/tmp/test", entries=[
        JDEntry(path="/tmp/test/alpha.md", role_id="alpha",
                frontmatter=JDFrontmatter(title="Alpha"), body=""),
        JDEntry(path="/tmp/test/beta.md", role_id="beta",
                frontmatter=JDFrontmatter(title="Beta"), body=""),
    ])
    md = render_report_markdown(corpus, extractions, landscape)
    assert "department — skill landscape" in md
    assert "Shared skills" in md
    assert "Python" in md
    assert "Alpha-only" in md
    assert "Beta-only" in md
