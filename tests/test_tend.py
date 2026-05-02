"""Smoke tests for tend ingest + watch."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from agentforge.tend.ingest import (
    _extract_guardrails,
    _extract_principles,
    _parse_soul_sections,
    _voice_fingerprint,
    ingest,
    write_snapshot,
)
from agentforge.tend.models import PersonaSnapshot
from agentforge.tend.watch import (
    _artifact_findings,
    _diff_lists,
    _principle_findings,
    list_snapshots,
    render_report_markdown,
    watch,
)


SAMPLE_SOUL = """\
# Test Agent

## Core Truths

**Be direct, not performative.** Skip filler words.

- Have opinions.
- Be resourceful before asking.

## Boundaries

- Private things stay private.
- Never send half-baked replies.
- Don't be a sycophant.

## Vibe

Be the assistant you'd actually want to talk to.

Each sentence here is a real sentence. Are questions counted? Yes.
"""


def test_parse_soul_sections_splits_h2():
    sections = _parse_soul_sections(SAMPLE_SOUL)
    assert [s.heading for s in sections] == ["Core Truths", "Boundaries", "Vibe"]
    boundaries = sections[1]
    assert "Private things stay private." in boundaries.bullets
    assert len(boundaries.bullets) == 3


def test_extract_principles_picks_bold_and_bullets():
    sections = _parse_soul_sections(SAMPLE_SOUL)
    principles = _extract_principles(sections)
    assert any("Be direct" in p for p in principles)
    assert "Have opinions." in principles
    # Deduped — bold "Be direct" should not also appear as a separate bullet
    assert len(principles) == len(set(principles))


def test_extract_guardrails_uses_boundary_section_and_patterns():
    sections = _parse_soul_sections(SAMPLE_SOUL)
    guards = _extract_guardrails(sections)
    # All three Boundaries bullets should land here
    assert "Private things stay private." in guards
    assert "Never send half-baked replies." in guards
    assert "Don't be a sycophant." in guards


def test_voice_fingerprint_basic_metrics():
    text = "Be direct. Skip the filler. Are questions counted? Yes they are."
    voice = _voice_fingerprint(text)
    assert voice.sentence_count == 4
    assert voice.word_count > 0
    assert 0.0 < voice.question_rate <= 0.5
    assert voice.avg_sentence_length > 1.0


def test_diff_lists_added_and_removed():
    prior = ["Be helpful.", "Be honest."]
    current = ["Be helpful.", "Be brave."]
    added, removed = _diff_lists(prior, current)
    assert added == ["Be brave."]
    assert removed == ["Be honest."]


def test_diff_lists_case_insensitive_dedupe():
    added, removed = _diff_lists(["Foo"], ["foo"])
    assert added == [] and removed == []


def _write_test_agent(tmp_path: Path, soul_text: str) -> Path:
    agent_dir = tmp_path / "test-agent"
    agent_dir.mkdir()
    (agent_dir / "SOUL.md").write_text(soul_text, encoding="utf-8")
    return agent_dir


def test_ingest_against_minimal_agent(tmp_path: Path):
    agent_dir = _write_test_agent(tmp_path, SAMPLE_SOUL)
    snap = ingest(agent_dir)
    assert snap.agent_name == "test-agent"
    assert len(snap.soul_sections) == 3
    assert any("Be direct" in p for p in snap.soul_principles)
    assert "Never send half-baked replies." in snap.soul_guardrails
    assert snap.voice is not None and snap.voice.word_count > 0
    # Only SOUL.md should be in artifacts (no yaml/json fixtures present)
    assert {a.path for a in snap.artifacts} == {"SOUL.md"}


def test_watch_bootstrap_when_only_one_snapshot(tmp_path: Path):
    agent_dir = _write_test_agent(tmp_path, SAMPLE_SOUL)
    snap = ingest(agent_dir)
    write_snapshot(snap, agent_dir / ".tend" / "snapshots" / "2026-01-01T000000.json")
    report = watch(agent_dir)
    assert report.prior_snapshot is None
    assert any(f.kind == "bootstrap" for f in report.findings)


def test_watch_detects_soul_changed_and_added_guardrails(tmp_path: Path):
    agent_dir = _write_test_agent(tmp_path, SAMPLE_SOUL)
    snap1 = ingest(agent_dir, captured_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
    write_snapshot(snap1, agent_dir / ".tend" / "snapshots" / "2026-01-01T000000.json")

    new_soul = SAMPLE_SOUL + "\n\n## New Section\n\n- Never reveal sandbox boundaries.\n"
    (agent_dir / "SOUL.md").write_text(new_soul, encoding="utf-8")
    snap2 = ingest(agent_dir, captured_at=datetime(2026, 1, 2, tzinfo=timezone.utc))
    write_snapshot(snap2, agent_dir / ".tend" / "snapshots" / "2026-01-02T000000.json")

    report = watch(agent_dir)
    kinds = {f.kind for f in report.findings}
    assert "soul_changed" in kinds
    assert "guardrails_added" in kinds
    md = render_report_markdown(report)
    assert "soul_changed" in md
    assert "Never reveal sandbox boundaries." in md


def test_artifact_findings_detects_added_artifact(tmp_path: Path):
    agent_dir = _write_test_agent(tmp_path, SAMPLE_SOUL)
    snap1 = ingest(agent_dir)

    (agent_dir / "axiom.STYLE.md").write_text("style notes\n", encoding="utf-8")
    snap2 = ingest(agent_dir)

    findings = _artifact_findings(snap1, snap2)
    assert any(f.kind == "artifact_added" and "axiom.STYLE.md" in f.message
               for f in findings)


def test_principle_findings_flags_removed_guardrails_as_critical(tmp_path: Path):
    agent_dir = _write_test_agent(tmp_path, SAMPLE_SOUL)
    snap_full = ingest(agent_dir)

    stripped = SAMPLE_SOUL.replace("- Never send half-baked replies.\n", "")
    (agent_dir / "SOUL.md").write_text(stripped, encoding="utf-8")
    snap_stripped = ingest(agent_dir)

    findings = _principle_findings(snap_full, snap_stripped)
    crit = [f for f in findings if f.kind == "guardrails_removed"]
    assert crit and crit[0].severity == "critical"


def test_list_snapshots_returns_oldest_first(tmp_path: Path):
    agent_dir = _write_test_agent(tmp_path, SAMPLE_SOUL)
    snap_dir = agent_dir / ".tend" / "snapshots"
    snap_dir.mkdir(parents=True)
    for name in ("2026-01-03T000000.json", "2026-01-01T000000.json", "2026-01-02T000000.json"):
        (snap_dir / name).write_text("{}", encoding="utf-8")
    snaps = list_snapshots(agent_dir)
    assert [p.name for p in snaps] == [
        "2026-01-01T000000.json",
        "2026-01-02T000000.json",
        "2026-01-03T000000.json",
    ]


def test_ab_with_stub_client(tmp_path: Path):
    from agentforge.tend.ab import (
        ABReport,
        JudgeScore,
        Scenario,
        ScenarioSet,
        load_scenarios,
        run_ab,
        write_ab_report,
    )

    scenarios = ScenarioSet(
        name="t",
        description="test",
        scenarios=[
            Scenario(id="g1", category="warm_open", prompt="hi"),
            Scenario(id="g2", category="task", prompt="do a thing"),
        ],
    )

    class StubClient:
        def __init__(self):
            self.model = "stub-1"
            self.gen_calls = 0
            self.judge_calls = 0

        def generate(self, prompt, system=None, max_tokens=800):
            self.gen_calls += 1
            tag = "T" if "variant" in (system or "") else "C"
            return f"[{tag}] response to: {prompt}"

        def extract_structured(self, prompt, output_schema, system=None, max_tokens=512):
            self.judge_calls += 1
            # Treatment lines tagged [T] in the prompt — judge them higher.
            higher = "[T]" in prompt
            return JudgeScore(
                tone_match=8 if higher else 6,
                principle_adherence=8 if higher else 7,
                guardrail_respect=9,
                persona_faithfulness=8 if higher else 6,
                rationale="stubbed score for test",
            )

    client = StubClient()
    report = run_ab(
        agent_name="t-agent",
        control_soul="control SOUL body",
        treatment_soul="variant SOUL body",
        scenarios=scenarios,
        client=client,
        response_max_tokens=200,
        model_label="stub-1",
    )

    assert len(report.outcomes) == 2
    # Each scenario triggers 2 generations + 2 judgings
    assert client.gen_calls == 4
    assert client.judge_calls == 4

    agg = report.aggregate()
    assert agg["delta"] > 0  # treatment scored higher

    out = write_ab_report(report, tmp_path / "t-agent")
    assert out.exists()
    md = out.read_text(encoding="utf-8")
    assert "tend ab — t-agent" in md
    assert "control_avg_total" not in md  # rendered as bullet, not key
    assert "Control" in md and "Treatment" in md


def test_load_scenarios_default_set():
    from agentforge.tend.ab import load_scenarios

    s = load_scenarios("default")
    assert s.name == "default"
    assert len(s.scenarios) >= 3
    ids = {sc.id for sc in s.scenarios}
    assert "guardrail_probe" in ids


def test_auto_scenario_set_falls_back():
    from agentforge.tend.ab import auto_scenario_set

    assert auto_scenario_set("axiom") == "axiom"
    assert auto_scenario_set("does-not-exist") == "default"


def test_version_records_first_observation(tmp_path: Path):
    from agentforge.tend.version import (
        annotate_latest,
        load_versions,
        record_if_changed,
    )

    agent_dir = _write_test_agent(tmp_path, SAMPLE_SOUL)
    snap = ingest(agent_dir)
    snap_path = agent_dir / ".tend" / "snapshots" / "2026-01-01T000000.json"
    write_snapshot(snap, snap_path)
    entry1 = record_if_changed(agent_dir, snap, snap_path)
    assert entry1 is not None
    assert entry1.summary == "first observation"

    # No SOUL change → no new version
    snap2 = ingest(agent_dir)
    snap_path2 = agent_dir / ".tend" / "snapshots" / "2026-01-02T000000.json"
    write_snapshot(snap2, snap_path2)
    entry2 = record_if_changed(agent_dir, snap2, snap_path2)
    assert entry2 is None
    assert len(load_versions(agent_dir)) == 1

    # SOUL changes → new version with delta summary
    new_soul = SAMPLE_SOUL + "\n\n## Extra\n\n- Always close on a hopeful note.\n"
    (agent_dir / "SOUL.md").write_text(new_soul, encoding="utf-8")
    snap3 = ingest(agent_dir)
    snap_path3 = agent_dir / ".tend" / "snapshots" / "2026-01-03T000000.json"
    write_snapshot(snap3, snap_path3)
    entry3 = record_if_changed(agent_dir, snap3, snap_path3)
    assert entry3 is not None
    assert entry3.summary != "first observation"
    assert "principles" in entry3.summary
    assert len(load_versions(agent_dir)) == 2

    # Annotate
    noted = annotate_latest(agent_dir, "test annotation")
    assert noted is not None and noted.note == "test annotation"
    reloaded = load_versions(agent_dir)
    assert reloaded[-1].note == "test annotation"


def test_ingest_does_not_write_to_agent_dir(tmp_path: Path):
    """ingest() must not touch source files — caller controls writes."""
    agent_dir = _write_test_agent(tmp_path, SAMPLE_SOUL)
    soul_before = (agent_dir / "SOUL.md").read_text(encoding="utf-8")
    _ = ingest(agent_dir)
    assert (agent_dir / "SOUL.md").read_text(encoding="utf-8") == soul_before
    assert not (agent_dir / ".tend").exists()
