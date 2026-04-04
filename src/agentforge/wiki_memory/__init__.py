"""Wiki-memory layer for AgentForge agents.

Structured, linked, durable knowledge store that sits alongside each agent's
episodic MEMORY. See docs/wiki-memory-design.md for the full design.

Public API:
    WikiStore     — read/write wiki pages, manage the index
    Page          — single wiki page (entity or concept)
    CandidateFact — fact queued for review
    promote       — promote a candidate onto its target page
"""
from .promote import promote
from .schema import CandidateFact, Page
from .store import WikiStore

__all__ = ["CandidateFact", "Page", "WikiStore", "promote"]
