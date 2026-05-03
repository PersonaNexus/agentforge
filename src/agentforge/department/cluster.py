"""Skill clustering across roles in a JD corpus.

Given per-role extraction results, find skills that recur across
multiple roles (candidates for shared department-level skills) vs ones
that are role-specific. Phase 1.0 uses normalized-name matching, which
catches the obvious cases (e.g. ``CI/CD`` appearing in 4 of 5 roles).
Phase 1.1 will add LLM-judged equivalence merging for cases where the
phrasing diverges (``"Postgres SQL"`` vs ``"PostgreSQL"`` vs
``"relational databases"``).
"""

from __future__ import annotations

import re
from collections import defaultdict

from pydantic import BaseModel, Field

from agentforge.models.extracted_skills import ExtractionResult


class SkillCluster(BaseModel):
    """A skill that may appear under different phrasings across roles."""

    canonical_name: str
    member_names: list[str] = Field(default_factory=list)
    role_ids: list[str] = Field(default_factory=list)
    category: str | None = None
    importance_max: str | None = None  # max importance seen across roles

    @property
    def role_count(self) -> int:
        return len(self.role_ids)

    @property
    def is_shared(self) -> bool:
        return self.role_count >= 2


class SkillLandscape(BaseModel):
    """The full skill picture across a corpus."""

    schema_version: str = "1"
    role_count: int
    role_ids: list[str] = Field(default_factory=list)
    clusters: list[SkillCluster] = Field(default_factory=list)

    @property
    def shared_clusters(self) -> list[SkillCluster]:
        return [c for c in self.clusters if c.is_shared]

    @property
    def role_specific_clusters(self) -> list[SkillCluster]:
        return [c for c in self.clusters if not c.is_shared]


_NORMALIZE_RE = re.compile(r"[^a-z0-9]+")
_IMPORTANCE_ORDER = {"required": 3, "preferred": 2, "nice_to_have": 1}


def _normalize(name: str) -> str:
    """Aggressive normalization for naive cluster keying."""
    s = name.lower().strip()
    s = _NORMALIZE_RE.sub(" ", s)
    s = " ".join(s.split())
    # Common abbreviation expansions / contractions to merge close phrasings.
    replacements = [
        ("ci cd", "ci/cd"),
        ("github actions", "ci/cd"),  # specific tools fold to category
        ("postgresql", "postgres"),
        ("postgres sql", "postgres"),
        ("react js", "react"),
        ("type script", "typescript"),
        ("aws cloud", "aws"),
    ]
    for src, dst in replacements:
        if s == src:
            s = dst
    return s


def cluster_skills(
    extractions: dict[str, ExtractionResult],
) -> SkillLandscape:
    """Build a skill landscape from a {role_id: ExtractionResult} mapping.

    Phase 1.0 uses normalized-name keying — fast, deterministic, no LLM
    calls. Members within a cluster are the original (un-normalized)
    skill names as they appeared in each role.
    """
    bucket: dict[str, dict] = defaultdict(lambda: {
        "names": [],
        "roles": [],
        "categories": [],
        "importances": [],
    })

    for role_id, result in extractions.items():
        for skill in result.skills:
            key = _normalize(skill.name)
            if not key:
                continue
            entry = bucket[key]
            entry["names"].append(skill.name)
            entry["roles"].append(role_id)
            entry["categories"].append(getattr(skill.category, "value", str(skill.category)))
            entry["importances"].append(getattr(skill.importance, "value", str(skill.importance)))

    clusters: list[SkillCluster] = []
    for key, e in bucket.items():
        # Pick the most-common category as canonical
        cat = max(set(e["categories"]), key=e["categories"].count) if e["categories"] else None
        # Pick max importance seen
        imp = None
        if e["importances"]:
            imp = max(e["importances"], key=lambda i: _IMPORTANCE_ORDER.get(i, 0))
        # Canonical name = most-frequent original phrasing
        names = e["names"]
        canonical = max(set(names), key=names.count)
        # Dedupe role IDs while preserving first-seen order
        seen = set()
        roles_dedup: list[str] = []
        for r in e["roles"]:
            if r not in seen:
                seen.add(r)
                roles_dedup.append(r)
        clusters.append(SkillCluster(
            canonical_name=canonical,
            member_names=sorted(set(names)),
            role_ids=roles_dedup,
            category=cat,
            importance_max=imp,
        ))

    # Sort: shared first (most roles), then role-specific (alphabetical)
    clusters.sort(key=lambda c: (-c.role_count, c.canonical_name.lower()))
    role_ids = sorted(extractions.keys())
    return SkillLandscape(
        role_count=len(extractions),
        role_ids=role_ids,
        clusters=clusters,
    )
