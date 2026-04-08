"""Types for the layered prompt composer."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum


class LayerType(IntEnum):
    """Prompt layer types in priority order (lower = higher priority)."""
    PERSONA = 1
    RULES = 2
    MEMORY = 3
    WIKI = 4
    SKILLS = 5
    TASK_CONTEXT = 6


# Default budget share per layer type (fraction of total budget).
DEFAULT_BUDGET_SHARES: dict[LayerType, float] = {
    LayerType.PERSONA: 0.30,
    LayerType.RULES: 0.15,
    LayerType.MEMORY: 0.15,
    LayerType.WIKI: 0.15,
    LayerType.SKILLS: 0.15,
    LayerType.TASK_CONTEXT: 0.10,
}


@dataclass
class LayerConfig:
    """Configuration for a single layer type."""
    budget_share: float = 0.15
    required: bool = False          # required layers never get truncated to zero
    section_marker: str = ""        # e.g. "## Persona" — rendered before content


@dataclass
class PromptLayer:
    """A single layer of composed prompt content."""
    layer_type: LayerType
    content: str
    source: str = ""                # e.g. "SOUL.md", "MEMORY.md", "wiki:ai-gateway"
    estimated_tokens: int = 0       # filled by budget module
    truncated: bool = False         # True if content was trimmed for budget

    @property
    def priority(self) -> int:
        return int(self.layer_type)


@dataclass
class AssembledPrompt:
    """Final assembled prompt with metadata."""
    text: str
    total_tokens: int
    layers_included: list[str] = field(default_factory=list)   # layer names
    layers_truncated: list[str] = field(default_factory=list)  # layers that were trimmed
    budget_total: int = 0
    budget_used: int = 0
