"""Tests for ``agentforge drill`` (Phase 1.0)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from agentforge.drill import ingest as ingest_mod
from agentforge.drill import scan as scan_mod
from agentforge.drill import version as version_mod
from agentforge.drill import watch as watch_mod
from agentforge.drill.models import SkillInventory, snapshot_path


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "skill-corpus" / "dev-skills"


# ---------- ingest ----------


def test_ingest_detects_parent_layout():
    inv = ingest_mod.ingest(FIXTURE_ROOT)
    assert inv.layout == "parent"
    slugs = {d.slug for d in inv.skills}
    assert slugs == {"ship-pr", "review-code", "run-tests", "decommissioned"}


def test_ingest_detects_single_layout(tmp_path):
    skill = tmp_path / "single-skill"
    skill.mkdir()
    (skill / "SKILL.md").write_text(
        "---\ndescription: solo\nallowed-tools: [Read]\n---\n# Solo\n\nRead.\n",
        encoding="utf-8",
    )
    inv = ingest_mod.ingest(skill)
    assert inv.layout == "single"
    assert inv.total_skills == 1
    assert inv.skills[0].slug == "single-skill"


def test_ingest_marks_missing_skill_md():
    inv = ingest_mod.ingest(FIXTURE_ROOT)
    decom = next(d for d in inv.skills if d.slug == "decommissioned")
    assert decom.has_skill_md is False
    assert "SKILL.md missing" in decom.notes


def test_ingest_extracts_frontmatter_and_body_features():
    inv = ingest_mod.ingest(FIXTURE_ROOT)
    ship = next(d for d in inv.skills if d.slug == "ship-pr")
    assert ship.has_skill_md
    assert ship.description.startswith("Open a pull request")
    assert "Bash" in ship.allowed_tools
    assert ship.body_word_count > 20
    assert ship.body_sha256 != ""
    # Frontmatter description was harvested.
    assert "description" in ship.frontmatter_keys
    # Templates file picked up as a referenced file (it's in backticks in the body).
    assert any("pr-body.md" in r for r in ship.referenced_files)


def test_ingest_is_deterministic_modulo_timestamp(tmp_path):
    fixed = datetime(2026, 5, 3, 12, 0, 0, tzinfo=timezone.utc)
    a = ingest_mod.ingest(FIXTURE_ROOT, captured_at=fixed)
    b = ingest_mod.ingest(FIXTURE_ROOT, captured_at=fixed)
    # Same fixed timestamp → identical JSON output.
    assert a.model_dump_json() == b.model_dump_json()


def test_ingest_rejects_missing_directory(tmp_path):
    with pytest.raises(FileNotFoundError):
        ingest_mod.ingest(tmp_path / "nope")


# ---------- scan ----------


def test_scan_flags_missing_skill_md():
    inv = ingest_mod.ingest(FIXTURE_ROOT)
    report = scan_mod.scan(inv)
    missing = [f for f in report.findings if f.kind == "missing_file"]
    assert len(missing) == 1
    assert missing[0].skill == "decommissioned"
    assert missing[0].severity == "critical"


def test_scan_flags_overlap_between_similar_descriptions():
    inv = ingest_mod.ingest(FIXTURE_ROOT)
    report = scan_mod.scan(inv)
    overlap = [f for f in report.findings if f.kind == "overlap"]
    # ship-pr and review-code share "pull request" + "walk through review"
    # vocabulary — should clear the 0.55 jaccard threshold.
    assert len(overlap) >= 1
    msg = overlap[0].message
    assert "ship-pr" in msg and "review-code" in msg


def test_scan_flags_tool_sprawl_by_count():
    inv = ingest_mod.ingest(FIXTURE_ROOT)
    report = scan_mod.scan(inv)
    sprawl = [f for f in report.findings if f.kind == "tool_sprawl" and f.skill == "review-code"]
    # review-code declares 10 allowed-tools (above default threshold of 8).
    assert any("allowed-tools" in f.message for f in sprawl)


def test_scan_flags_broken_reference():
    inv = ingest_mod.ingest(FIXTURE_ROOT)
    report = scan_mod.scan(inv)
    broken = [f for f in report.findings if f.kind == "broken_reference"]
    # ship-pr references CHANGELOG.md in its body, but no such file exists in
    # the fixture's ship-pr folder.
    assert any(f.skill == "ship-pr" and "CHANGELOG.md" in f.message for f in broken)


def test_scan_bloat_threshold_is_configurable(tmp_path):
    # Build a skill with a known word count and tune the threshold below it.
    skill = tmp_path / "wordy"
    skill.mkdir()
    body = " ".join([f"word{i}" for i in range(120)])
    (skill / "SKILL.md").write_text(
        f"---\ndescription: x\nallowed-tools: [Read]\n---\n# Wordy\n\n{body}\n",
        encoding="utf-8",
    )
    inv = ingest_mod.ingest(skill)
    # Default threshold (1500) — no bloat.
    assert all(f.kind != "bloat" for f in scan_mod.scan(inv).findings)
    # Tight threshold (50) — should trip.
    report = scan_mod.scan(inv, bloat_threshold=50)
    assert any(f.kind == "bloat" and f.skill == "wordy" for f in report.findings)


def test_scan_renders_markdown_with_finding_groups():
    inv = ingest_mod.ingest(FIXTURE_ROOT)
    report = scan_mod.scan(inv)
    md = scan_mod.render_report_markdown(report)
    assert "drill scan" in md
    # Critical missing_file finding should anchor the report.
    assert "missing_file" in md
    assert "decommissioned" in md


# ---------- watch ----------


def test_watch_with_fewer_than_two_snapshots_returns_empty(tmp_path):
    inv = ingest_mod.ingest(FIXTURE_ROOT, captured_at=datetime(2026, 5, 3, tzinfo=timezone.utc))
    snap = snapshot_path(tmp_path, inv.captured_at)
    snap.parent.mkdir(parents=True, exist_ok=True)
    # Re-root the inventory at tmp_path so list_snapshots picks it up under tmp_path/.drill/.
    snap.write_text(inv.model_dump_json(), encoding="utf-8")

    report = watch_mod.watch(tmp_path)
    assert report.findings == []


def test_watch_diffs_two_snapshots(tmp_path):
    """Hand-craft prior/current inventories and verify all 4 finding kinds fire."""
    t0 = datetime(2026, 5, 3, 10, 0, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(hours=1)

    prior = SkillInventory.model_validate({
        "skill_dir": str(tmp_path),
        "layout": "parent",
        "captured_at": t0.isoformat(),
        "skills": [
            {"slug": "alpha", "path": "alpha", "description": "do alpha",
             "body_word_count": 100, "body_sha256": "a"*64,
             "allowed_tools": ["Read"], "has_skill_md": True},
            {"slug": "to-remove", "path": "to-remove", "description": "old",
             "body_word_count": 50, "body_sha256": "b"*64,
             "allowed_tools": [], "has_skill_md": True},
        ],
        "total_skills": 2,
    })
    current = SkillInventory.model_validate({
        "skill_dir": str(tmp_path),
        "layout": "parent",
        "captured_at": t1.isoformat(),
        "skills": [
            # Body grew by 60% and added a tool; description churned.
            {"slug": "alpha", "path": "alpha", "description": "do alpha differently",
             "body_word_count": 160, "body_sha256": "c"*64,
             "allowed_tools": ["Read", "Bash"], "has_skill_md": True},
            # Brand-new skill.
            {"slug": "newcomer", "path": "newcomer", "description": "fresh",
             "body_word_count": 80, "body_sha256": "d"*64,
             "allowed_tools": ["Read"], "has_skill_md": True},
        ],
        "total_skills": 2,
    })

    snap_dir = tmp_path / ".drill" / "snapshots"
    snap_dir.mkdir(parents=True)
    p_prior = snap_dir / f"{t0.strftime('%Y-%m-%dT%H%M%S')}.json"
    p_current = snap_dir / f"{t1.strftime('%Y-%m-%dT%H%M%S')}.json"
    p_prior.write_text(prior.model_dump_json(), encoding="utf-8")
    p_current.write_text(current.model_dump_json(), encoding="utf-8")

    report = watch_mod.watch(tmp_path)
    kinds = {f.kind for f in report.findings}
    assert "skill_added" in kinds  # newcomer
    assert "skill_removed" in kinds  # to-remove
    assert "body_grew" in kinds  # alpha
    assert "tools_expanded" in kinds  # alpha
    assert "description_changed" in kinds  # alpha


# ---------- version ----------


def test_version_records_first_observation(tmp_path):
    skill = tmp_path / "first"
    skill.mkdir()
    (skill / "SKILL.md").write_text(
        "---\ndescription: x\nallowed-tools: [Read]\n---\n# x\n\nbody one\n",
        encoding="utf-8",
    )
    inv = ingest_mod.ingest(skill)
    snap = snapshot_path(skill, inv.captured_at)
    snap.parent.mkdir(parents=True, exist_ok=True)
    snap.write_text(inv.model_dump_json(), encoding="utf-8")

    entry = version_mod.record_if_changed(skill, inv, snap)
    assert entry is not None
    assert entry.skill_count == 1
    assert entry.summary == "first observation"


def test_version_skips_unchanged_inventory(tmp_path):
    skill = tmp_path / "stable"
    skill.mkdir()
    (skill / "SKILL.md").write_text(
        "---\ndescription: x\nallowed-tools: [Read]\n---\n# x\n\nbody one\n",
        encoding="utf-8",
    )
    inv1 = ingest_mod.ingest(skill)
    snap1 = snapshot_path(skill, inv1.captured_at)
    snap1.parent.mkdir(parents=True, exist_ok=True)
    snap1.write_text(inv1.model_dump_json(), encoding="utf-8")
    e1 = version_mod.record_if_changed(skill, inv1, snap1)
    assert e1 is not None

    # Re-ingest with no changes — fingerprint identical → no new entry.
    inv2 = ingest_mod.ingest(skill, captured_at=inv1.captured_at + timedelta(seconds=1))
    snap2 = snapshot_path(skill, inv2.captured_at)
    snap2.write_text(inv2.model_dump_json(), encoding="utf-8")
    e2 = version_mod.record_if_changed(skill, inv2, snap2)
    assert e2 is None
    assert len(version_mod.load_versions(skill)) == 1


def test_version_records_change(tmp_path):
    skill = tmp_path / "evolves"
    skill.mkdir()
    (skill / "SKILL.md").write_text(
        "---\ndescription: x\nallowed-tools: [Read]\n---\n# x\n\nv1 body\n",
        encoding="utf-8",
    )
    inv1 = ingest_mod.ingest(skill)
    snap1 = snapshot_path(skill, inv1.captured_at)
    snap1.parent.mkdir(parents=True, exist_ok=True)
    snap1.write_text(inv1.model_dump_json(), encoding="utf-8")
    version_mod.record_if_changed(skill, inv1, snap1)

    # Mutate body — fingerprint changes → new entry.
    (skill / "SKILL.md").write_text(
        "---\ndescription: x\nallowed-tools: [Read]\n---\n# x\n\nv2 body now longer\n",
        encoding="utf-8",
    )
    inv2 = ingest_mod.ingest(skill, captured_at=inv1.captured_at + timedelta(hours=1))
    snap2 = snapshot_path(skill, inv2.captured_at)
    snap2.write_text(inv2.model_dump_json(), encoding="utf-8")
    e2 = version_mod.record_if_changed(skill, inv2, snap2)
    assert e2 is not None
    assert "skills 1→1" in (e2.summary or "")
    assert len(version_mod.load_versions(skill)) == 2


def test_version_annotate_latest(tmp_path):
    skill = tmp_path / "annotate"
    skill.mkdir()
    (skill / "SKILL.md").write_text(
        "---\ndescription: x\nallowed-tools: [Read]\n---\n# x\n\nbody\n",
        encoding="utf-8",
    )
    inv = ingest_mod.ingest(skill)
    snap = snapshot_path(skill, inv.captured_at)
    snap.parent.mkdir(parents=True, exist_ok=True)
    snap.write_text(inv.model_dump_json(), encoding="utf-8")
    version_mod.record_if_changed(skill, inv, snap)

    e = version_mod.annotate_latest(skill, "shipped via PR #28")
    assert e is not None and e.note == "shipped via PR #28"
    # Persisted on disk.
    persisted = version_mod.load_versions(skill)
    assert persisted[-1].note == "shipped via PR #28"
