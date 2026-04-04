"""Tests for the wiki-memory MVP."""
from __future__ import annotations

import json

import pytest

from agentforge.wiki_memory import CandidateFact, Page, WikiStore, promote
from agentforge.wiki_memory.cli import main as cli_main
from agentforge.wiki_memory.schema import slugify


# ── schema ────────────────────────────────────────────────────────────────────

class TestSchema:
    def test_slugify(self):
        assert slugify("AI Gateway") == "ai-gateway"
        assert slugify("  Foo  &  Bar!! ") == "foo-bar"
        assert slugify("über Café") == "ber-caf"  # non-ASCII stripped

    def test_page_requires_kind_for_entity(self):
        with pytest.raises(ValueError, match="must specify a kind"):
            Page(id="x", title="X", type="entity")

    def test_concept_rejects_kind(self):
        with pytest.raises(ValueError, match="must not have a kind"):
            Page(id="x", title="X", type="concept", kind="project")

    def test_add_fact_dedupes_exact(self):
        p = Page(id="x", title="X", type="entity", kind="project")
        assert p.add_fact("Runs on port 8900", source="s1") is True
        # same claim, different case + trailing period → deduped
        assert p.add_fact("runs on port 8900.", source="s2") is False
        assert len(p.facts) == 1
        # source of the deduped attempt still recorded
        assert "s2" in p.sources

    def test_add_fact_bumps_confidence(self):
        p = Page(id="x", title="X", type="entity", kind="project", confidence="low")
        p.add_fact("claim1", source="s", confidence="high")
        assert p.confidence == "high"

    def test_candidate_fact_validates(self):
        with pytest.raises(ValueError):
            CandidateFact(
                subject_hint="X", claim="c", page_type="entity",
                kind=None, source="s",
            )


# ── store: I/O round-trip ─────────────────────────────────────────────────────

class TestStore:
    def test_save_and_reload(self, tmp_path):
        store = WikiStore(tmp_path)
        page = Page(
            id="ai-gateway", title="AI Gateway", type="entity", kind="project",
            aliases=["gateway"], tags=["infra"],
        )
        page.add_fact("Runs on port 8900", source="session:x", confidence="high")
        page.add_fact("Uses Gemma 4 E4B", source="session:y")
        store.save(page)

        loaded = store.load("ai-gateway")
        assert loaded is not None
        assert loaded.title == "AI Gateway"
        assert loaded.kind == "project"
        assert loaded.aliases == ["gateway"]
        assert loaded.tags == ["infra"]
        assert len(loaded.facts) == 2
        assert loaded.facts[0].claim == "Runs on port 8900"
        assert loaded.facts[0].confidence == "high"
        assert loaded.confidence == "high"

    def test_concept_no_kind_on_disk(self, tmp_path):
        store = WikiStore(tmp_path)
        page = Page(id="agents", title="Agent Orchestration", type="concept")
        store.save(page)
        loaded = store.load("agents")
        assert loaded is not None
        assert loaded.kind is None

    def test_index_built_and_used(self, tmp_path):
        store = WikiStore(tmp_path)
        page = Page(
            id="ai-gateway", title="AI Gateway", type="entity", kind="project",
            aliases=["gateway", "gw"],
        )
        store.save(page)
        index = json.loads((tmp_path / "index.json").read_text())
        assert "ai-gateway" in index["pages"]
        assert index["aliases"]["gateway"] == "ai-gateway"
        assert index["aliases"]["gw"] == "ai-gateway"
        assert index["aliases"]["ai gateway"] == "ai-gateway"

    def test_resolve_by_slug_alias_and_title(self, tmp_path):
        store = WikiStore(tmp_path)
        store.save(Page(
            id="ai-gateway", title="AI Gateway", type="entity", kind="project",
            aliases=["gateway"],
        ))
        assert store.resolve("ai-gateway").id == "ai-gateway"
        assert store.resolve("AI Gateway").id == "ai-gateway"
        assert store.resolve("gateway").id == "ai-gateway"
        # substring fallback
        assert store.resolve("Gate").id == "ai-gateway"
        assert store.resolve("nothing-here") is None

    def test_search(self, tmp_path):
        store = WikiStore(tmp_path)
        p1 = Page(id="ai-gateway", title="AI Gateway", type="entity", kind="project")
        p1.add_fact("Runs on port 8900", source="s")
        store.save(p1)
        store.save(Page(
            id="openclaw", title="OpenClaw", type="entity", kind="system",
            aliases=["claw"],
        ))
        ids = {p.id for p in store.search("gateway")}
        assert ids == {"ai-gateway"}
        assert {p.id for p in store.search("claw")} == {"openclaw"}
        assert {p.id for p in store.search("port 8900")} == {"ai-gateway"}
        assert store.search("") == []


# ── promotion pipeline ────────────────────────────────────────────────────────

class TestPromotion:
    def _cf(self, **kwargs):
        defaults = dict(
            subject_hint="AI Gateway",
            claim="Runs on port 8900",
            page_type="entity",
            kind="project",
            source="session:2026-04-04",
            confidence="medium",
            contributor="forge",
        )
        defaults.update(kwargs)
        return CandidateFact(**defaults)

    def test_promote_creates_new_page(self, tmp_path):
        store = WikiStore(tmp_path)
        page = promote(store, self._cf(), decision="accept")
        assert page is not None
        assert page.id == "ai-gateway"
        assert any("port 8900" in f.claim for f in page.facts)
        assert "forge" in page.contributors
        # Page persisted on disk.
        assert (tmp_path / "entities" / "project" / "ai-gateway.md").exists()

    def test_promote_resolves_existing_by_alias(self, tmp_path):
        store = WikiStore(tmp_path)
        store.save(Page(
            id="ai-gateway", title="AI Gateway", type="entity", kind="project",
            aliases=["gateway"],
        ))
        page = promote(store, self._cf(subject_hint="gateway"), decision="accept")
        assert page.id == "ai-gateway"  # resolved to existing — no dup page

    def test_reject_adds_nothing(self, tmp_path):
        store = WikiStore(tmp_path)
        result = promote(store, self._cf(), decision="reject")
        assert result is None
        assert not (tmp_path / "entities" / "project" / "ai-gateway.md").exists()

    def test_edit_replaces_claim(self, tmp_path):
        store = WikiStore(tmp_path)
        page = promote(
            store, self._cf(), decision="edit", edited_claim="Runs on port 8901",
        )
        assert any("8901" in f.claim for f in page.facts)
        assert not any("8900" in f.claim for f in page.facts)

    def test_promote_dedupes(self, tmp_path):
        store = WikiStore(tmp_path)
        promote(store, self._cf(source="s1"), decision="accept")
        page = promote(store, self._cf(source="s2"), decision="accept")
        assert len(page.facts) == 1
        assert "s2" in page.sources  # new source recorded on dedupe

    def test_queue_and_pending(self, tmp_path):
        store = WikiStore(tmp_path)
        store.queue_candidate(self._cf())
        store.queue_candidate(self._cf(claim="Uses Gemma 4 E4B"))
        pending = store.pending()
        assert len(pending) == 2
        # After promotion, fewer pending remain.
        promote(store, pending[0], decision="accept")
        assert len(store.pending()) == 1

    def test_review_audit_trail(self, tmp_path):
        store = WikiStore(tmp_path)
        promote(store, self._cf(), decision="accept")
        promote(store, self._cf(claim="other"), decision="reject")
        reviewed = (tmp_path / "pending" / "reviewed.jsonl").read_text().splitlines()
        assert len(reviewed) == 2
        decisions = [json.loads(r)["decision"] for r in reviewed]
        assert decisions == ["accept", "reject"]

    def test_promote_rejects_empty_claim(self, tmp_path):
        store = WikiStore(tmp_path)
        with pytest.raises(ValueError, match="empty"):
            promote(store, self._cf(), decision="edit", edited_claim="   ")


# ── CLI smoke ─────────────────────────────────────────────────────────────────

class TestCLI:
    def test_add_show_search_roundtrip(self, tmp_path, capsys):
        root = str(tmp_path)
        assert cli_main([
            "--root", root, "add",
            "--title", "AI Gateway", "--type", "entity", "--kind", "project",
            "--alias", "gateway", "--fact", "Runs on 8900", "--source", "s",
        ]) == 0
        assert cli_main(["--root", root, "show", "ai-gateway"]) == 0
        out = capsys.readouterr().out
        assert "AI Gateway" in out
        assert "Runs on 8900" in out

        assert cli_main(["--root", root, "search", "gateway"]) == 0
        assert "ai-gateway" in capsys.readouterr().out

    def test_candidate_then_promote_all(self, tmp_path, capsys):
        root = str(tmp_path)
        assert cli_main([
            "--root", root, "candidate",
            "--subject", "AI Gateway", "--claim", "uses Gemma",
            "--type", "entity", "--kind", "project", "--source", "s",
        ]) == 0
        assert cli_main(["--root", root, "pending"]) == 0
        assert "uses Gemma" in capsys.readouterr().out
        assert cli_main(["--root", root, "promote", "--accept-all"]) == 0
        # Pending should be empty after accept-all.
        assert cli_main(["--root", root, "pending"]) == 0
        assert "no pending" in capsys.readouterr().out
