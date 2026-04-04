"""Promotion pipeline: candidate facts → wiki pages."""
from __future__ import annotations

from typing import Literal

from .schema import CandidateFact, Page
from .store import WikiStore

Decision = Literal["accept", "reject", "edit"]


def promote(
    store: WikiStore,
    candidate: CandidateFact,
    decision: Decision = "accept",
    *,
    edited_claim: str | None = None,
    note: str = "",
) -> Page | None:
    """Apply a reviewer decision to a candidate.

    - ``accept``: resolve the candidate to its target page (creating a draft if
      nothing matches), add the fact, save the page, and append the candidate
      to the reviewed audit trail.
    - ``reject``: record the decision only; no page is modified.
    - ``edit``: same as accept but uses ``edited_claim`` as the claim text.

    Returns the saved ``Page`` for accept/edit, or ``None`` for reject.
    """
    if decision == "reject":
        store.record_review(candidate, "reject", note=note)
        return None

    claim = edited_claim if decision == "edit" else candidate.claim
    if not claim or not claim.strip():
        raise ValueError("claim is empty; cannot promote")

    target = store.resolve(candidate.subject_hint)
    if target is None:
        target = store.get_or_create(
            candidate.subject_hint,
            type=candidate.page_type,
            kind=candidate.kind,
        )

    added = target.add_fact(
        claim=claim,
        source=candidate.source or "unknown",
        confidence=candidate.confidence,
        contributor=candidate.contributor or None,
    )
    store.save(target)
    store.record_review(
        candidate,
        decision,
        note=note or (f"dedup: existing claim on {target.id}" if not added else ""),
    )
    return target
