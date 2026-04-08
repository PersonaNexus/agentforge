"""Persona resolver — loads SOUL.md or PersonaNexus identity YAML."""
from __future__ import annotations

from pathlib import Path

from ..types import LayerType, PromptLayer


class PersonaResolver:
    """Load an agent's persona from a SOUL.md file or raw text.

    In production, this would integrate with PersonaNexus
    ``SystemPromptCompiler`` to render a compiled identity. For now,
    it reads a markdown SOUL file directly.
    """

    def __init__(self, soul_path: str | Path | None = None):
        self.soul_path = Path(soul_path) if soul_path else None

    def resolve(self, fallback_text: str = "") -> PromptLayer:
        content = ""
        source = ""
        if self.soul_path and self.soul_path.exists():
            content = self.soul_path.read_text(encoding="utf-8").strip()
            source = str(self.soul_path.name)
        elif fallback_text:
            content = fallback_text.strip()
            source = "inline"
        return PromptLayer(
            layer_type=LayerType.PERSONA,
            content=content,
            source=source,
        )
