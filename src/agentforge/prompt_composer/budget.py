"""Token estimation and budget allocation."""
from __future__ import annotations

from .types import DEFAULT_BUDGET_SHARES, LayerConfig, LayerType, PromptLayer


def estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 characters per token for English text.

    Good enough for budgeting; swap to tiktoken for precision later.
    """
    if not text:
        return 0
    return max(1, len(text) // 4)


def allocate_budgets(
    layers: list[PromptLayer],
    total_budget: int,
    config: dict[LayerType, LayerConfig] | None = None,
) -> dict[LayerType, int]:
    """Allocate token budgets to each layer.

    Layers that use less than their share donate the surplus downward
    (to lower-priority layers) proportionally.
    """
    shares = {
        lt: (config[lt].budget_share if config and lt in config else DEFAULT_BUDGET_SHARES.get(lt, 0.10))
        for lt in LayerType
    }

    # Initial allocation.
    budgets: dict[LayerType, int] = {
        lt: int(total_budget * shares[lt]) for lt in LayerType
    }

    # Populate token estimates.
    actual: dict[LayerType, int] = {}
    for layer in layers:
        layer.estimated_tokens = estimate_tokens(layer.content)
        actual[layer.layer_type] = layer.estimated_tokens

    # Redistribute surplus from layers that underuse their budget.
    surplus = 0
    recipients: list[LayerType] = []
    for lt in sorted(LayerType):
        used = actual.get(lt, 0)
        allocated = budgets[lt]
        if used < allocated:
            surplus += allocated - used
            budgets[lt] = used  # shrink to actual
        elif used > allocated:
            recipients.append(lt)

    # Distribute surplus to over-budget layers, proportionally by need.
    if surplus > 0 and recipients:
        total_need = sum(actual[lt] - budgets[lt] for lt in recipients)
        for lt in recipients:
            need = actual[lt] - budgets[lt]
            grant = int(surplus * need / total_need) if total_need > 0 else 0
            budgets[lt] += grant

    return budgets


def truncate_to_budget(text: str, token_budget: int) -> tuple[str, bool]:
    """Truncate text to fit within a token budget.

    Returns (truncated_text, was_truncated).
    """
    if estimate_tokens(text) <= token_budget:
        return text, False
    # Truncate by character count (budget * 4 chars/token).
    char_limit = max(0, token_budget * 4)
    if char_limit == 0:
        return "", True
    truncated = text[:char_limit]
    # Try to break at a line boundary.
    last_newline = truncated.rfind("\n")
    if last_newline > char_limit * 0.7:
        truncated = truncated[:last_newline]
    return truncated.rstrip() + "\n[... truncated for token budget]", True
