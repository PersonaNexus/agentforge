"""Tests for the shared ``agentforge.day2`` package."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

import pytest
import typer
from pydantic import BaseModel

from agentforge.day2 import (
    FileTooLargeError,
    FrontmatterParseError,
    annotate_latest_version,
    commit_label,
    count_severities,
    git_state,
    load_jsonl_versions,
    read_text_capped,
    render_findings_markdown,
    render_version_log,
    split_frontmatter,
    try_rev_parse,
    validate_dir,
    walk_files_no_symlinks,
)


# ---------- frontmatter ----------


def test_split_frontmatter_extracts_yaml_and_body():
    fm, body, notes = split_frontmatter("---\ntitle: x\n---\n\nbody\n")
    assert fm == {"title": "x"}
    assert "body" in body
    assert notes == []


def test_split_frontmatter_no_block_returns_text_unchanged():
    fm, body, notes = split_frontmatter("# heading\n\nbody\n")
    assert fm == {}
    assert body.startswith("# heading")
    assert notes == []


def test_split_frontmatter_lenient_mode_appends_note_on_bad_yaml():
    fm, body, notes = split_frontmatter("---\n: : invalid : :\n---\n\nbody\n")
    assert fm == {}
    assert any("YAML parse failed" in n for n in notes)


def test_split_frontmatter_strict_mode_raises_on_bad_yaml():
    with pytest.raises(FrontmatterParseError):
        split_frontmatter("---\n: : invalid : :\n---\n\nbody\n", strict=True)


def test_split_frontmatter_strict_mode_raises_on_non_mapping():
    with pytest.raises(FrontmatterParseError, match="not a YAML mapping"):
        split_frontmatter("---\n- just\n- a\n- list\n---\n\nbody\n", strict=True)


# ---------- safe_io ----------


def test_read_text_capped_reads_small_files(tmp_path):
    p = tmp_path / "small.md"
    p.write_text("hello world", encoding="utf-8")
    assert read_text_capped(p) == "hello world"


def test_read_text_capped_raises_on_oversize(tmp_path):
    p = tmp_path / "big.md"
    p.write_bytes(b"x" * 200)
    with pytest.raises(FileTooLargeError):
        read_text_capped(p, max_bytes=100)


def test_walk_files_skips_symlinks(tmp_path):
    real = tmp_path / "real.md"
    real.write_text("hi", encoding="utf-8")
    target = tmp_path / "target.txt"
    target.write_text("secret", encoding="utf-8")
    link = tmp_path / "link.md"
    os.symlink(target, link)

    found = sorted(p.name for p in walk_files_no_symlinks(tmp_path))
    assert found == ["real.md", "target.txt"]
    # link.md (the symlink) is NOT in found, but its target IS (because target
    # is a real file in tmp_path). The symlink itself is correctly skipped.
    assert "link.md" not in found


def test_walk_files_skips_symlinked_directories(tmp_path):
    real_dir = tmp_path / "real"
    real_dir.mkdir()
    (real_dir / "ok.md").write_text("ok", encoding="utf-8")
    outside = tmp_path.parent / f"outside-{tmp_path.name}"
    outside.mkdir(exist_ok=True)
    (outside / "leak.md").write_text("leak", encoding="utf-8")
    try:
        link_dir = tmp_path / "linked"
        os.symlink(outside, link_dir, target_is_directory=True)
        found = sorted(str(p.relative_to(tmp_path)) for p in walk_files_no_symlinks(tmp_path))
        assert "real/ok.md" in found
        # Files under the symlinked directory should NOT be reachable.
        assert not any("leak.md" in f for f in found)
    finally:
        for p in outside.iterdir():
            p.unlink()
        outside.rmdir()


# ---------- vcs ----------


def test_try_rev_parse_returns_none_outside_repo(tmp_path):
    assert try_rev_parse(tmp_path) is None


def test_git_state_returns_none_outside_repo(tmp_path):
    commit, dirty = git_state(tmp_path)
    assert commit is None and dirty is None


# ---------- version_log ----------


class _FakeEntry(BaseModel):
    n: int
    note: str | None = None


def test_load_versions_skips_malformed_lines(tmp_path):
    p = tmp_path / "log.jsonl"
    p.write_text(
        '{"n": 1}\n'
        'not-json-at-all\n'
        '{"n": 2}\n'
        '\n'
        '{"n": "wrong-type"}\n',
        encoding="utf-8",
    )
    out = load_jsonl_versions(p, _FakeEntry)
    assert [e.n for e in out] == [1, 2]


def test_annotate_latest_writes_note(tmp_path):
    p = tmp_path / "log.jsonl"
    p.write_text('{"n": 1}\n{"n": 2}\n', encoding="utf-8")
    e = annotate_latest_version(p, _FakeEntry, "shipped")
    assert e is not None and e.note == "shipped" and e.n == 2
    # Only the latest got annotated.
    persisted = load_jsonl_versions(p, _FakeEntry)
    assert persisted[0].note is None
    assert persisted[1].note == "shipped"


def test_annotate_latest_returns_none_for_empty_log(tmp_path):
    p = tmp_path / "log.jsonl"
    assert annotate_latest_version(p, _FakeEntry, "x") is None


def test_render_version_log_uses_row_renderer():
    entries = [_FakeEntry(n=1), _FakeEntry(n=2, note="hello")]
    out = render_version_log(
        entries,
        title="test log",
        empty_text="(empty)",
        row_renderer=lambda i, e: [f"## v{i} n={e.n}", *([f"- note: {e.note}"] if e.note else [])],
    )
    assert "# test log" in out
    assert "## v1 n=1" in out and "## v2 n=2" in out
    assert "- note: hello" in out


def test_render_version_log_empty():
    assert "(empty)" in render_version_log([], title="x", empty_text="(empty)", row_renderer=lambda i, e: [])


def test_commit_label_formats_dirty():
    assert commit_label("abcdef0123456789", True) == "abcdef01*"
    assert commit_label("abcdef0123456789", False) == "abcdef01"
    assert commit_label(None, None) == "—"


# ---------- finding_render ----------


class _FakeFinding(BaseModel):
    kind: str
    severity: str
    message: str
    skill: str | None = None
    detail: str | None = None


def test_count_severities():
    findings = [
        _FakeFinding(kind="a", severity="critical", message="x"),
        _FakeFinding(kind="a", severity="warn", message="y"),
        _FakeFinding(kind="b", severity="warn", message="z"),
    ]
    counts = count_severities(findings)
    assert counts["critical"] == 1
    assert counts["warn"] == 2
    assert counts["info"] == 0


def test_render_findings_markdown_groups_by_kind_in_order():
    findings = [
        _FakeFinding(kind="bloat", severity="warn", message="b1"),
        _FakeFinding(kind="missing_file", severity="critical", message="m1", skill="s1"),
        _FakeFinding(kind="missing_file", severity="critical", message="m2", skill="s2"),
    ]
    out = render_findings_markdown(
        title="scan",
        metadata_lines=[],
        findings=findings,
        kind_order=["missing_file", "bloat"],
    )
    # kind_order respected: missing_file group appears before bloat.
    assert out.index("## missing_file") < out.index("## bloat")
    # Counts in summary line.
    assert "critical: 2, warn: 1, info: 0" in out
    # Skill scope rendered.
    assert "`s1` —" in out
    assert "`s2` —" in out


def test_render_findings_markdown_no_grouping_renders_flat():
    findings = [
        _FakeFinding(kind="x", severity="info", message="one"),
        _FakeFinding(kind="y", severity="info", message="two", detail="more"),
    ]
    out = render_findings_markdown(
        title="watch",
        metadata_lines=["_run-time_"],
        findings=findings,
        group_by_kind=False,
    )
    assert "## x" not in out and "## y" not in out
    assert "**[info]**" in out
    assert "  - more" in out


def test_render_findings_markdown_empty():
    out = render_findings_markdown(
        title="scan",
        metadata_lines=[],
        findings=[],
        empty_text="_clean_",
    )
    assert "_clean_" in out


# ---------- cli_validators ----------


def test_validate_dir_resolves_existing(tmp_path):
    out = validate_dir(tmp_path, entity="thing")
    assert out == tmp_path.resolve()


def test_validate_dir_rejects_missing(tmp_path):
    with pytest.raises(typer.BadParameter, match="thing does not exist"):
        validate_dir(tmp_path / "nope", entity="thing")


def test_validate_dir_rejects_file(tmp_path):
    f = tmp_path / "f.txt"
    f.write_text("x", encoding="utf-8")
    with pytest.raises(typer.BadParameter):
        validate_dir(f, entity="thing")
