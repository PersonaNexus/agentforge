"""Rules resolver — loads CLAUDE.md, guardrails, and operating instructions."""
from __future__ import annotations

from pathlib import Path

from ..types import LayerType, PromptLayer


class RulesResolver:
    """Load operating rules from one or more instruction files.

    Typical sources: CLAUDE.md, guardrails sections from PersonaNexus identity,
    or inline rules passed by the orchestrator.
    """

    def __init__(self, paths: list[str | Path] | None = None):
        self.paths = [Path(p) for p in (paths or [])]

    def resolve(self, extra_rules: str = "") -> PromptLayer:
        parts: list[str] = []
        sources: list[str] = []
        for path in self.paths:
            if path.exists():
                parts.append(path.read_text(encoding="utf-8").strip())
                sources.append(path.name)
        if extra_rules:
            parts.append(extra_rules.strip())
            sources.append("inline")
        return PromptLayer(
            layer_type=LayerType.RULES,
            content="\n\n".join(parts),
            source=", ".join(sources),
        )
