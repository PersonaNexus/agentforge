"""Tests for the layered prompt composer."""
from __future__ import annotations

import pytest

from agentforge.prompt_composer import (
    AssembledPrompt,
    LayerConfig,
    LayerType,
    PromptComposer,
    PromptLayer,
)
from agentforge.prompt_composer.budget import allocate_budgets, estimate_tokens, truncate_to_budget
from agentforge.prompt_composer.resolvers import MemoryResolver, PersonaResolver, RulesResolver


# ── Budget ────────────────────────────────────────────────────────────────────

class TestBudget:
    def test_estimate_tokens(self):
        assert estimate_tokens("") == 0
        assert estimate_tokens("hello world") > 0
        # ~4 chars per token
        assert estimate_tokens("a" * 400) == 100

    def test_truncate_within_budget(self):
        text = "short text"
        result, was_truncated = truncate_to_budget(text, 100)
        assert result == text
        assert was_truncated is False

    def test_truncate_over_budget(self):
        text = "word " * 200  # ~1000 chars, ~250 tokens
        result, was_truncated = truncate_to_budget(text, 50)
        assert was_truncated is True
        assert len(result) < len(text)
        assert "[... truncated" in result

    def test_truncate_zero_budget(self):
        result, was_truncated = truncate_to_budget("some text", 0)
        assert result == ""
        assert was_truncated is True

    def test_allocate_budgets_basic(self):
        layers = [
            PromptLayer(LayerType.PERSONA, "x" * 400),  # 100 tokens
            PromptLayer(LayerType.RULES, "x" * 200),     # 50 tokens
        ]
        budgets = allocate_budgets(layers, total_budget=1000)
        # Persona gets 30% of 1000 = 300, but only needs 100
        assert budgets[LayerType.PERSONA] == 100
        # Rules gets 15% of 1000 = 150, needs 50
        assert budgets[LayerType.RULES] == 50

    def test_allocate_surplus_donation(self):
        layers = [
            PromptLayer(LayerType.PERSONA, "x" * 40),     # 10 tokens (uses 10 of 300)
            PromptLayer(LayerType.MEMORY, "x" * 4000),     # 1000 tokens (needs more than 150)
        ]
        budgets = allocate_budgets(layers, total_budget=1000)
        # Memory should get surplus from persona's unused allocation
        assert budgets[LayerType.MEMORY] > 150


# ── Composer ──────────────────────────────────────────────────────────────────

class TestComposer:
    def test_empty_composer(self):
        c = PromptComposer()
        result = c.assemble()
        assert result.text == ""
        assert result.total_tokens == 0

    def test_single_layer(self):
        c = PromptComposer()
        c.add_text(LayerType.PERSONA, "You are Forge, the engineering agent.")
        result = c.assemble()
        assert "Forge" in result.text
        assert "persona" in result.layers_included

    def test_layers_ordered_by_priority(self):
        c = PromptComposer()
        # Add in reverse order — should still render persona first
        c.add_text(LayerType.TASK_CONTEXT, "Current task: nightly build")
        c.add_text(LayerType.PERSONA, "You are Forge.")
        c.add_text(LayerType.RULES, "Never delete files without asking.")
        result = c.assemble()
        persona_pos = result.text.index("Forge")
        rules_pos = result.text.index("Never delete")
        task_pos = result.text.index("nightly build")
        assert persona_pos < rules_pos < task_pos

    def test_section_markers_rendered(self):
        c = PromptComposer()
        c.add_text(LayerType.PERSONA, "You are Forge.")
        c.add_text(LayerType.MEMORY, "Jim prefers Python.")
        result = c.assemble()
        assert "## Identity & Persona" in result.text
        assert "## Memory & Context" in result.text

    def test_xml_format(self):
        c = PromptComposer(format="xml")
        c.add_text(LayerType.PERSONA, "You are Forge.")
        result = c.assemble()
        assert "<persona>" in result.text
        assert "</persona>" in result.text

    def test_duplicate_layer_merged(self):
        c = PromptComposer()
        c.add_text(LayerType.MEMORY, "Fact 1", source="file1.md")
        c.add_text(LayerType.MEMORY, "Fact 2", source="file2.md")
        result = c.assemble()
        assert "Fact 1" in result.text
        assert "Fact 2" in result.text
        assert result.layers_included.count("memory") == 1

    def test_truncation_reported(self):
        # Persona with huge content, small budget
        c = PromptComposer(total_budget=100)
        c.add_text(LayerType.PERSONA, "word " * 500)  # way over 30 token budget
        result = c.assemble()
        assert "truncated" in result.layers_truncated or len(result.text) < len("word " * 500)

    def test_clear(self):
        c = PromptComposer()
        c.add_text(LayerType.PERSONA, "x")
        c.clear()
        assert c.assemble().text == ""

    def test_all_six_layers(self):
        c = PromptComposer(total_budget=10000)
        c.add_text(LayerType.PERSONA, "Persona content")
        c.add_text(LayerType.RULES, "Rules content")
        c.add_text(LayerType.MEMORY, "Memory content")
        c.add_text(LayerType.WIKI, "Wiki content")
        c.add_text(LayerType.SKILLS, "Skills content")
        c.add_text(LayerType.TASK_CONTEXT, "Task content")
        result = c.assemble()
        assert len(result.layers_included) == 6
        # All content present
        for expected in ["Persona", "Rules", "Memory", "Wiki", "Skills", "Task"]:
            assert expected in result.text

    def test_assembled_prompt_metadata(self):
        c = PromptComposer(total_budget=5000)
        c.add_text(LayerType.PERSONA, "You are Forge.")
        result = c.assemble()
        assert result.budget_total == 5000
        assert result.budget_used > 0
        assert result.total_tokens > 0


# ── Resolvers ─────────────────────────────────────────────────────────────────

class TestResolvers:
    def test_persona_resolver_from_file(self, tmp_path):
        soul = tmp_path / "SOUL.md"
        soul.write_text("# Forge\nYou are the engineering agent.")
        r = PersonaResolver(soul_path=soul)
        layer = r.resolve()
        assert layer.layer_type == LayerType.PERSONA
        assert "engineering agent" in layer.content
        assert layer.source == "SOUL.md"

    def test_persona_resolver_fallback(self):
        r = PersonaResolver()
        layer = r.resolve(fallback_text="You are a helpful assistant.")
        assert "helpful assistant" in layer.content

    def test_persona_resolver_missing_file(self):
        r = PersonaResolver(soul_path="/nonexistent/SOUL.md")
        layer = r.resolve()
        assert layer.content == ""

    def test_rules_resolver(self, tmp_path):
        claude_md = tmp_path / "CLAUDE.md"
        claude_md.write_text("Never delete files without asking.")
        r = RulesResolver(paths=[claude_md])
        layer = r.resolve()
        assert "delete files" in layer.content
        assert layer.source == "CLAUDE.md"

    def test_rules_resolver_with_extra(self, tmp_path):
        r = RulesResolver()
        layer = r.resolve(extra_rules="Always use Python.")
        assert "Python" in layer.content

    def test_memory_resolver(self, tmp_path):
        index = tmp_path / "MEMORY.md"
        index.write_text("# Memory\n- Jim prefers Python")
        mem_dir = tmp_path / "memory"
        mem_dir.mkdir()
        (mem_dir / "feedback.md").write_text("Use pytest for testing.")
        r = MemoryResolver(memory_index=index, memory_dir=mem_dir)
        layer = r.resolve()
        assert "Jim prefers Python" in layer.content
        assert "pytest" in layer.content

    def test_memory_resolver_empty(self):
        r = MemoryResolver()
        layer = r.resolve()
        assert layer.content == ""


# ── Integration ───────────────────────────────────────────────────────────────

class TestIntegration:
    def test_resolvers_into_composer(self, tmp_path):
        # Set up files
        soul = tmp_path / "SOUL.md"
        soul.write_text("You are Forge, the engineering agent.")
        claude = tmp_path / "CLAUDE.md"
        claude.write_text("Always commit with descriptive messages.")
        mem_index = tmp_path / "MEMORY.md"
        mem_index.write_text("Jim prefers Python over TypeScript.")

        # Resolve layers
        persona = PersonaResolver(soul_path=soul).resolve()
        rules = RulesResolver(paths=[claude]).resolve()
        memory = MemoryResolver(memory_index=mem_index).resolve()

        # Compose
        c = PromptComposer(total_budget=5000)
        c.add(persona)
        c.add(rules)
        c.add(memory)
        result = c.assemble()

        assert "Forge" in result.text
        assert "commit" in result.text
        assert "Python" in result.text
        assert len(result.layers_included) == 3
        # Correct order
        assert result.text.index("Forge") < result.text.index("commit")
        assert result.text.index("commit") < result.text.index("Python")
