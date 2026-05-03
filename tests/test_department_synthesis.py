"""Tests for department Phase 1.1 — team synthesis."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml

from agentforge.corpus import load_corpus
from agentforge.department.cluster import cluster_skills
from agentforge.department.conductor import (
    build_conductor_identity,
    render_conductor_skill_md,
    render_conductor_yaml,
)
from agentforge.department.handoffs import (
    Handoff,
    HandoffGraph,
    detect_handoffs,
    detect_handoffs_llm,
    render_orchestration_yaml,
)
from agentforge.department.readme import render_readme
from agentforge.department.synthesize_team import synthesize_team
from agentforge.models.extracted_skills import (
    ExtractedRole,
    ExtractedSkill,
    ExtractionResult,
    SkillCategory,
    SkillImportance,
    SkillProficiency,
)


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "jd-corpus" / "dev-team"


# --- helpers ---


def _skill(name: str, importance=SkillImportance.REQUIRED) -> ExtractedSkill:
    return ExtractedSkill(
        name=name,
        category=SkillCategory.HARD,
        proficiency=SkillProficiency.ADVANCED,
        importance=importance,
        context=f"used for {name}",
    )


def _result(role_title: str, *skills: ExtractedSkill, purpose: str = "") -> ExtractionResult:
    return ExtractionResult(
        role=ExtractedRole(
            title=role_title,
            seniority="senior",
            domain="software-engineering",
            purpose=purpose or f"do {role_title} work",
            responsibilities=[f"do {role_title} work A", f"do {role_title} work B"],
        ),
        skills=list(skills),
    )


def _stub_extractor(extractions_by_role_id: dict[str, ExtractionResult]):
    def _extract(entry):
        # entry is a JDEntry; key by role_id.
        return extractions_by_role_id[entry.role_id]
    return _extract


# --- handoffs ---


def test_handoff_graph_renders_yaml_round_trip():
    graph = HandoffGraph(
        role_ids=["a", "b"],
        handoffs=[
            Handoff(from_role="a", to_role="b", trigger="t", artifact="art", description="d"),
        ],
    )
    text = render_orchestration_yaml(graph)
    parsed = yaml.safe_load(text)
    assert parsed["role_ids"] == ["a", "b"]
    assert parsed["handoffs"][0]["from"] == "a"
    assert parsed["handoffs"][0]["to"] == "b"
    assert parsed["handoffs"][0]["artifact"] == "art"


def test_detect_handoffs_no_client_returns_empty_graph():
    corpus = load_corpus(FIXTURE_ROOT)
    g = detect_handoffs(corpus, {}, client=None)
    assert g.handoffs == []
    assert len(g.role_ids) == len(corpus)


def test_detect_handoffs_llm_drops_invalid_role_ids():
    corpus = load_corpus(FIXTURE_ROOT)
    extractions = {e.role_id: _result(e.frontmatter.title) for e in corpus}

    fake_judge = MagicMock()
    fake_judge.extract_structured.return_value = type(
        "R", (),
        {"handoffs": [
            type("E", (), {"from_role": "backend-engineer", "to_role": "qa-engineer",
                           "trigger": "PR opened", "artifact": "merged PR",
                           "description": ""})(),
            type("E", (), {"from_role": "ghost", "to_role": "backend-engineer",
                           "trigger": "x", "artifact": "y", "description": ""})(),
            type("E", (), {"from_role": "backend-engineer", "to_role": "backend-engineer",
                           "trigger": "self", "artifact": "self", "description": ""})(),
        ]}
    )()

    g = detect_handoffs_llm(corpus, extractions, fake_judge)
    # ghost edge dropped, self-edge dropped, valid edge kept
    assert len(g.handoffs) == 1
    assert g.handoffs[0].from_role == "backend-engineer"
    assert g.handoffs[0].to_role == "qa-engineer"


# --- conductor ---


def test_conductor_identity_has_routing_table():
    corpus = load_corpus(FIXTURE_ROOT)
    extractions = {
        e.role_id: _result(e.frontmatter.title, _skill("Python"))
        for e in corpus
    }
    graph = HandoffGraph(role_ids=[e.role_id for e in corpus])

    identity = build_conductor_identity(corpus, extractions, graph, "dev-team")
    assert identity["metadata"]["id"] == "dev-team-conductor"
    assert "routing_table" in identity["expertise"]
    assert len(identity["expertise"]["routing_table"]) == len(corpus)
    # YAML round-trips
    text = render_conductor_yaml(identity)
    parsed = yaml.safe_load(text)
    assert parsed["metadata"]["id"] == "dev-team-conductor"


def test_conductor_skill_md_lists_handoffs():
    corpus = load_corpus(FIXTURE_ROOT)
    extractions = {e.role_id: _result(e.frontmatter.title) for e in corpus}
    graph = HandoffGraph(
        role_ids=[e.role_id for e in corpus],
        handoffs=[Handoff(
            from_role="backend-engineer", to_role="qa-engineer",
            trigger="PR opened", artifact="merged PR",
        )],
    )
    md = render_conductor_skill_md("dev-team", corpus, extractions, graph)
    assert "Roster" in md
    assert "Handoffs" in md
    assert "`backend-engineer`" in md
    assert "merged PR" in md


# --- readme ---


def test_render_readme_deterministic_includes_handoffs_and_shared():
    corpus = load_corpus(FIXTURE_ROOT)
    extractions = {
        e.role_id: _result(e.frontmatter.title, _skill("Python"), _skill("Postgres"))
        for e in corpus
    }
    landscape = cluster_skills(extractions)
    graph = HandoffGraph(
        role_ids=[e.role_id for e in corpus],
        handoffs=[Handoff(from_role="backend-engineer", to_role="qa-engineer",
                          artifact="merged PR")],
    )
    md = render_readme("dev-team", corpus, extractions, landscape, graph)
    assert "Dev-Team" in md or "dev-team" in md.lower()
    assert "Roster" in md
    assert "Shared capabilities" in md
    assert "merged PR" in md
    assert "## Layout" in md


# --- end-to-end synthesis ---


def test_synthesize_team_emits_full_layout(tmp_path):
    corpus = load_corpus(FIXTURE_ROOT)
    # Stub extractions: every role has Python + Postgres + a unique skill.
    extractions = {}
    for e in corpus:
        extractions[e.role_id] = _result(
            e.frontmatter.title,
            _skill("Python"),
            _skill("Postgres"),
            _skill(f"{e.role_id}-only"),
            purpose=f"own {e.frontmatter.title.lower()}",
        )

    out = tmp_path / "team-out"
    artifacts = synthesize_team(
        corpus, out,
        department_name="dev-team",
        extractions=extractions,
        client=None,
        use_llm_handoffs=False,
        use_llm_brief=False,
    )

    # Top-level files
    assert Path(artifacts.readme_path).exists()
    assert Path(artifacts.orchestration_path).exists()
    assert (out / "README.md").read_text().startswith("# Dev-Team Department") \
        or "department" in (out / "README.md").read_text().lower()

    # orchestration.yaml is valid YAML even with no handoffs
    parsed = yaml.safe_load((out / "orchestration.yaml").read_text())
    assert parsed["handoffs"] == []
    assert set(parsed["role_ids"]) == {e.role_id for e in corpus}

    # Shared library has at least Python+Postgres clusters
    shared_dir = out / "_shared" / "skills"
    assert shared_dir.is_dir()
    shared_files = sorted(p.name for p in shared_dir.iterdir())
    assert any("python" in n for n in shared_files)
    assert any("postgres" in n for n in shared_files)

    # Each role has identity.yaml + SKILL.md + the cross-link section
    for entry in corpus:
        role_dir = out / entry.role_id
        assert (role_dir / "identity.yaml").exists()
        skill_md = (role_dir / "SKILL.md").read_text()
        assert "Shared with the team" in skill_md
        assert "../_shared/skills/" in skill_md

    # Conductor exists
    assert (out / "_conductor" / "identity.yaml").exists()
    assert (out / "_conductor" / "SKILL.md").exists()

    # Artifact summary matches reality
    assert artifacts.shared_cluster_count >= 2  # Python + Postgres at minimum
    assert artifacts.handoff_count == 0
    assert len(artifacts.role_artifacts) == len(corpus)


def test_synthesize_team_target_plain_suppresses_identity_yaml(tmp_path):
    corpus = load_corpus(FIXTURE_ROOT)
    extractions = {
        e.role_id: _result(e.frontmatter.title, _skill("Python"))
        for e in corpus
    }
    out = tmp_path / "team-plain"
    artifacts = synthesize_team(
        corpus, out, department_name="dev-team",
        extractions=extractions, target="plain",
    )
    for r in artifacts.role_artifacts:
        assert r.identity_yaml_path is None
        assert not (out / r.role_id / "identity.yaml").exists()
    # Conductor identity.yaml also suppressed
    assert artifacts.conductor_identity_path is None
    assert not (out / "_conductor" / "identity.yaml").exists()
    # SKILL.md still emitted
    assert (out / "_conductor" / "SKILL.md").exists()


def test_synthesize_team_keep_identity_yaml_overrides_plain(tmp_path):
    corpus = load_corpus(FIXTURE_ROOT)
    extractions = {
        e.role_id: _result(e.frontmatter.title, _skill("Python"))
        for e in corpus
    }
    out = tmp_path / "team-plain-keep"
    artifacts = synthesize_team(
        corpus, out, department_name="dev-team",
        extractions=extractions, target="plain", keep_identity_yaml=True,
    )
    for r in artifacts.role_artifacts:
        assert r.identity_yaml_path is not None
        assert (out / r.role_id / "identity.yaml").exists()
    assert artifacts.conductor_identity_path is not None


def test_synthesize_team_with_extract_callable_is_idempotent(tmp_path):
    """Re-running synthesize_team into the same dir should be safe."""
    corpus = load_corpus(FIXTURE_ROOT)
    extractions = {
        e.role_id: _result(e.frontmatter.title, _skill("Python"))
        for e in corpus
    }
    out = tmp_path / "team"
    a1 = synthesize_team(corpus, out, department_name="dev-team",
                         extractions=extractions)
    files1 = {p.relative_to(out) for p in out.rglob("*") if p.is_file()}
    a2 = synthesize_team(corpus, out, department_name="dev-team",
                         extractions=extractions)
    files2 = {p.relative_to(out) for p in out.rglob("*") if p.is_file()}
    assert files1 == files2
    assert a1.shared_cluster_count == a2.shared_cluster_count


def test_synthesize_team_requires_extractions_or_extract(tmp_path):
    corpus = load_corpus(FIXTURE_ROOT)
    with pytest.raises(ValueError, match="extractions"):
        synthesize_team(corpus, tmp_path / "x", department_name="dev-team")
