"""Tend — day-2+ persona maintenance for AgentForge.

Where AgentForge bootstraps an agent (one-shot JD → identity), Tend keeps
an existing agent healthy over time:

- ``tend ingest`` reads SOUL/identity/memory artifacts and produces a
  structured PersonaSnapshot.
- ``tend watch`` diffs snapshots and surfaces drift, semantic SOUL changes,
  and promotion candidates (guardrails appearing in memory but missing
  from SOUL).

Tend never edits an agent's source files. All output goes to
``<agent-dir>/.tend/``.
"""

from agentforge.tend.models import (
    PersonaSnapshot,
    SoulSection,
    VoiceFingerprint,
)

__all__ = ["PersonaSnapshot", "SoulSection", "VoiceFingerprint"]
