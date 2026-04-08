"""PromptComposer — assemble typed layers into a system prompt."""
from __future__ import annotations

from .budget import allocate_budgets, estimate_tokens, truncate_to_budget
from .types import AssembledPrompt, LayerConfig, LayerType, PromptLayer


# Default section markers per layer type.
_SECTION_MARKERS: dict[LayerType, str] = {
    LayerType.PERSONA: "## Identity & Persona",
    LayerType.RULES: "## Operating Rules",
    LayerType.MEMORY: "## Memory & Context",
    LayerType.WIKI: "## Knowledge (Wiki)",
    LayerType.SKILLS: "## Skills & Capabilities",
    LayerType.TASK_CONTEXT: "## Current Task",
}


class PromptComposer:
    """Compose multiple prompt layers into a single system prompt.

    Usage::

        composer = PromptComposer(total_budget=8000)
        composer.add(PromptLayer(LayerType.PERSONA, content="You are Forge..."))
        composer.add(PromptLayer(LayerType.RULES, content="Never delete files..."))
        composer.add(PromptLayer(LayerType.MEMORY, content="Jim prefers Python..."))
        result = composer.assemble()
        print(result.text)
    """

    def __init__(
        self,
        total_budget: int = 8000,
        config: dict[LayerType, LayerConfig] | None = None,
        format: str = "markdown",  # "markdown" | "xml"
    ):
        self.total_budget = total_budget
        self.config = config or {}
        self.format = format
        self._layers: list[PromptLayer] = []

    def add(self, layer: PromptLayer) -> None:
        """Add a prompt layer. Duplicate layer types are merged (content concatenated)."""
        for existing in self._layers:
            if existing.layer_type == layer.layer_type:
                existing.content = existing.content.rstrip() + "\n\n" + layer.content.lstrip()
                if layer.source:
                    existing.source = f"{existing.source}, {layer.source}" if existing.source else layer.source
                return
        self._layers.append(layer)

    def add_text(self, layer_type: LayerType, content: str, source: str = "") -> None:
        """Convenience: add a layer from raw text."""
        self.add(PromptLayer(layer_type=layer_type, content=content, source=source))

    def assemble(self) -> AssembledPrompt:
        """Assemble all layers into a final prompt.

        Layers are:
        1. Sorted by priority (persona first, task_context last)
        2. Budget-allocated with surplus donation
        3. Truncated if over budget
        4. Rendered with section markers
        """
        if not self._layers:
            return AssembledPrompt(text="", total_tokens=0)

        # Sort by priority.
        sorted_layers = sorted(self._layers, key=lambda l: l.priority)

        # Allocate budgets.
        budgets = allocate_budgets(sorted_layers, self.total_budget, self.config)

        # Truncate and render.
        parts: list[str] = []
        included: list[str] = []
        truncated_names: list[str] = []
        total_tokens_used = 0

        for layer in sorted_layers:
            if not layer.content.strip():
                continue

            budget = budgets.get(layer.layer_type, 0)
            content, was_truncated = truncate_to_budget(layer.content, budget)
            layer.truncated = was_truncated

            if not content.strip():
                continue

            # Section marker.
            marker = self.config.get(layer.layer_type, LayerConfig()).section_marker
            if not marker:
                marker = _SECTION_MARKERS.get(layer.layer_type, "")

            if self.format == "xml":
                tag = layer.layer_type.name.lower()
                parts.append(f"<{tag}>\n{content.strip()}\n</{tag}>")
            else:
                if marker:
                    parts.append(f"{marker}\n\n{content.strip()}")
                else:
                    parts.append(content.strip())

            tokens = estimate_tokens(content)
            total_tokens_used += tokens
            included.append(layer.layer_type.name.lower())
            if was_truncated:
                truncated_names.append(layer.layer_type.name.lower())

        text = "\n\n".join(parts)

        return AssembledPrompt(
            text=text,
            total_tokens=estimate_tokens(text),
            layers_included=included,
            layers_truncated=truncated_names,
            budget_total=self.total_budget,
            budget_used=total_tokens_used,
        )

    def clear(self) -> None:
        self._layers.clear()
