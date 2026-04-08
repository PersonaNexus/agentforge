"""Layered prompt composer for AgentForge agents.

Treats prompt construction as composable layers (persona, rules, memory,
wiki, skills, task context) with typed priorities and token budgeting.

See docs/layered-prompt-architecture.md for the full design.
"""
from .composer import PromptComposer
from .types import AssembledPrompt, LayerConfig, LayerType, PromptLayer

__all__ = ["AssembledPrompt", "LayerConfig", "LayerType", "PromptComposer", "PromptLayer"]
