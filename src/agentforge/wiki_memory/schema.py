"""Page and candidate schemas for wiki-memory."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Literal

PageType = Literal["entity", "concept"]
EntityKind = Literal["person", "project", "system", "org", "place", "other"]
Confidence = Literal["high", "medium", "low"]

_VALID_PAGE_TYPES: tuple[PageType, ...] = ("entity", "concept")
_VALID_KINDS: tuple[EntityKind, ...] = (
    "person", "project", "system", "org", "place", "other",
)
_VALID_CONFIDENCE: tuple[Confidence, ...] = ("high", "medium", "low")


def slugify(text: str) -> str:
    """Produce a filesystem-safe slug from a title. Stable across calls."""
    s = text.strip().lower()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s


def today_iso() -> str:
    return date.today().isoformat()


@dataclass
class Fact:
    """A single claim attached to a page."""
    claim: str
    source: str
    added: str = field(default_factory=today_iso)
    confidence: Confidence = "medium"

    def to_line(self) -> str:
        return (
            f"- {self.claim} "
            f"_(source: {self.source}, confidence: {self.confidence}, added: {self.added})_"
        )


@dataclass
class Page:
    """A single wiki page — entity or concept."""
    id: str                       # stable slug, primary key
    title: str
    type: PageType
    kind: EntityKind | None = None   # only for type=entity
    aliases: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    created: str = field(default_factory=today_iso)
    updated: str = field(default_factory=today_iso)
    contributors: list[str] = field(default_factory=list)
    confidence: Confidence = "medium"
    sources: list[str] = field(default_factory=list)
    related: list[str] = field(default_factory=list)
    summary: str = ""
    facts: list[Fact] = field(default_factory=list)
    body_extra: str = ""          # anything after ## Facts (## History, etc.)

    def __post_init__(self) -> None:
        if self.type not in _VALID_PAGE_TYPES:
            raise ValueError(f"type must be one of {_VALID_PAGE_TYPES}, got {self.type!r}")
        if self.type == "entity" and self.kind is None:
            raise ValueError("entity pages must specify a kind")
        if self.type == "concept" and self.kind is not None:
            raise ValueError("concept pages must not have a kind")
        if self.kind is not None and self.kind not in _VALID_KINDS:
            raise ValueError(f"kind must be one of {_VALID_KINDS}, got {self.kind!r}")
        if self.confidence not in _VALID_CONFIDENCE:
            raise ValueError(
                f"confidence must be one of {_VALID_CONFIDENCE}, got {self.confidence!r}"
            )

    def add_fact(
        self,
        claim: str,
        source: str,
        confidence: Confidence = "medium",
        contributor: str | None = None,
    ) -> bool:
        """Append a fact if not an exact duplicate. Returns True if added."""
        normalized = _normalize_claim(claim)
        for existing in self.facts:
            if _normalize_claim(existing.claim) == normalized:
                # Dedupe: same claim → record the new source but skip the fact.
                if source not in self.sources:
                    self.sources.append(source)
                return False
        self.facts.append(Fact(claim=claim.strip(), source=source, confidence=confidence))
        if source not in self.sources:
            self.sources.append(source)
        if contributor and contributor not in self.contributors:
            self.contributors.append(contributor)
        self.updated = today_iso()
        # Bump page confidence to the max of contributing facts.
        self.confidence = _max_confidence(self.confidence, confidence)
        return True


def _normalize_claim(claim: str) -> str:
    return re.sub(r"\s+", " ", claim.strip().lower().rstrip("."))


def _max_confidence(a: Confidence, b: Confidence) -> Confidence:
    rank = {"low": 0, "medium": 1, "high": 2}
    return a if rank[a] >= rank[b] else b


@dataclass
class CandidateFact:
    """A fact captured from a session, queued for reviewer decision."""
    subject_hint: str              # free-text name/title of the target
    claim: str
    page_type: PageType            # entity | concept
    kind: EntityKind | None = None
    source: str = ""
    confidence: Confidence = "medium"
    contributor: str = ""
    captured: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))

    def __post_init__(self) -> None:
        if self.page_type not in _VALID_PAGE_TYPES:
            raise ValueError(f"page_type must be one of {_VALID_PAGE_TYPES}")
        if self.page_type == "entity" and self.kind is None:
            raise ValueError("entity candidates must specify kind")
        if self.confidence not in _VALID_CONFIDENCE:
            raise ValueError(f"confidence must be one of {_VALID_CONFIDENCE}")
