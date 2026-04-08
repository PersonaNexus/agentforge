"""Memory resolver — loads MEMORY.md and feedback files."""
from __future__ import annotations

from pathlib import Path

from ..types import LayerType, PromptLayer


class MemoryResolver:
    """Load agent memory from a MEMORY.md index and optional memory directory.

    Reads the index file and, if a memory directory exists, concatenates
    the most recently modified memory files up to a character limit.
    """

    def __init__(
        self,
        memory_index: str | Path | None = None,
        memory_dir: str | Path | None = None,
        max_files: int = 10,
    ):
        self.memory_index = Path(memory_index) if memory_index else None
        self.memory_dir = Path(memory_dir) if memory_dir else None
        self.max_files = max_files

    def resolve(self, extra_context: str = "") -> PromptLayer:
        parts: list[str] = []
        sources: list[str] = []

        # MEMORY.md index.
        if self.memory_index and self.memory_index.exists():
            parts.append(self.memory_index.read_text(encoding="utf-8").strip())
            sources.append(self.memory_index.name)

        # Individual memory files (most recent first).
        if self.memory_dir and self.memory_dir.is_dir():
            files = sorted(
                self.memory_dir.glob("*.md"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )[:self.max_files]
            for f in files:
                content = f.read_text(encoding="utf-8").strip()
                if content:
                    parts.append(f"### {f.stem}\n{content}")
                    sources.append(f.name)

        if extra_context:
            parts.append(extra_context.strip())
            sources.append("inline")

        return PromptLayer(
            layer_type=LayerType.MEMORY,
            content="\n\n".join(parts),
            source=", ".join(sources),
        )
