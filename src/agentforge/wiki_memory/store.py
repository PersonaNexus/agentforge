"""Storage layer for wiki-memory pages."""
from __future__ import annotations

import json
import re
from dataclasses import asdict
from pathlib import Path

import yaml

from .schema import (
    CandidateFact,
    Fact,
    Page,
    PageType,
    slugify,
    today_iso,
)

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)


class WikiStore:
    """Read/write wiki pages and manage the alias index.

    Layout under ``root``::

        entities/{person,project,system,org,place,other}/<slug>.md
        concepts/<slug>.md
        pending/<timestamp>-candidates.jsonl
        pending/reviewed.jsonl
        index.json
    """

    def __init__(self, root: str | Path):
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "pending").mkdir(exist_ok=True)

    # ── Paths ────────────────────────────────────────────────────────────────

    def _page_path(self, page: Page) -> Path:
        if page.type == "entity":
            assert page.kind is not None
            return self.root / "entities" / page.kind / f"{page.id}.md"
        return self.root / "concepts" / f"{page.id}.md"

    def _pending_file(self) -> Path:
        return self.root / "pending" / f"{today_iso()}-candidates.jsonl"

    def _reviewed_file(self) -> Path:
        return self.root / "pending" / "reviewed.jsonl"

    def _index_file(self) -> Path:
        return self.root / "index.json"

    # ── Page I/O ─────────────────────────────────────────────────────────────

    def save(self, page: Page) -> Path:
        path = self._page_path(page)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self._render(page), encoding="utf-8")
        self._refresh_index()
        return path

    def load(self, page_id: str) -> Page | None:
        """Load a page by its slug id, searching all known locations."""
        for path in self._all_page_paths():
            if path.stem == page_id:
                return self._parse(path)
        return None

    def get_or_create(
        self,
        title: str,
        *,
        type: PageType,
        kind: str | None = None,
        aliases: list[str] | None = None,
    ) -> Page:
        page_id = slugify(title)
        existing = self.load(page_id)
        if existing is not None:
            return existing
        return Page(
            id=page_id,
            title=title,
            type=type,
            kind=kind,  # type: ignore[arg-type]
            aliases=list(aliases or []),
        )

    def list_pages(self) -> list[Page]:
        return [self._parse(p) for p in sorted(self._all_page_paths())]

    def search(self, query: str) -> list[Page]:
        """Simple substring search across title/aliases/facts. Case-insensitive."""
        q = query.lower().strip()
        if not q:
            return []
        hits: list[Page] = []
        for page in self.list_pages():
            if q in page.title.lower():
                hits.append(page)
                continue
            if any(q in a.lower() for a in page.aliases):
                hits.append(page)
                continue
            if any(q in f.claim.lower() for f in page.facts):
                hits.append(page)
        return hits

    def resolve(self, subject_hint: str) -> Page | None:
        """Resolve a free-text subject hint to an existing page.

        Tier 1: exact slug match. Tier 2: alias match. Tier 3: title substring.
        """
        hint_slug = slugify(subject_hint)
        index = self._load_index()
        # Tier 1 — slug
        if hint_slug in index["pages"]:
            return self.load(hint_slug)
        # Tier 2 — alias
        target = index["aliases"].get(hint_slug) or index["aliases"].get(subject_hint.lower())
        if target:
            return self.load(target)
        # Tier 3 — title substring
        needle = subject_hint.lower().strip()
        for page in self.list_pages():
            if needle in page.title.lower():
                return page
        return None

    # ── Candidates ───────────────────────────────────────────────────────────

    def queue_candidate(self, candidate: CandidateFact) -> None:
        line = json.dumps(asdict(candidate), ensure_ascii=False)
        with self._pending_file().open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    def pending(self) -> list[CandidateFact]:
        """All candidates not yet reviewed."""
        reviewed_keys = self._reviewed_keys()
        out: list[CandidateFact] = []
        for path in sorted((self.root / "pending").glob("*-candidates.jsonl")):
            for raw in path.read_text(encoding="utf-8").splitlines():
                if not raw.strip():
                    continue
                data = json.loads(raw)
                cf = CandidateFact(**data)
                if _candidate_key(cf) not in reviewed_keys:
                    out.append(cf)
        return out

    def record_review(self, candidate: CandidateFact, decision: str, note: str = "") -> None:
        entry = {
            "key": _candidate_key(candidate),
            "decision": decision,
            "note": note,
            "reviewed_at": today_iso(),
            "candidate": asdict(candidate),
        }
        with self._reviewed_file().open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    # ── Index ────────────────────────────────────────────────────────────────

    def _refresh_index(self) -> None:
        index: dict[str, dict] = {"pages": {}, "aliases": {}}
        for path in self._all_page_paths():
            page = self._parse(path)
            index["pages"][page.id] = {
                "title": page.title,
                "type": page.type,
                "kind": page.kind,
                "path": str(path.relative_to(self.root)),
            }
            for alias in page.aliases:
                index["aliases"][alias.lower()] = page.id
            index["aliases"][page.title.lower()] = page.id
        self._index_file().write_text(
            json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def _load_index(self) -> dict:
        if not self._index_file().exists():
            self._refresh_index()
        return json.loads(self._index_file().read_text(encoding="utf-8"))

    def _all_page_paths(self) -> list[Path]:
        out: list[Path] = []
        entities_dir = self.root / "entities"
        if entities_dir.exists():
            out.extend(entities_dir.glob("*/*.md"))
        concepts_dir = self.root / "concepts"
        if concepts_dir.exists():
            out.extend(concepts_dir.glob("*.md"))
        return out

    def _reviewed_keys(self) -> set[str]:
        if not self._reviewed_file().exists():
            return set()
        keys: set[str] = set()
        for line in self._reviewed_file().read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                keys.add(json.loads(line)["key"])
            except Exception:
                continue
        return keys

    # ── Markdown render / parse ──────────────────────────────────────────────

    def _render(self, page: Page) -> str:
        fm = {
            "id": page.id,
            "title": page.title,
            "type": page.type,
            "kind": page.kind,
            "aliases": page.aliases,
            "tags": page.tags,
            "created": page.created,
            "updated": page.updated,
            "contributors": page.contributors,
            "confidence": page.confidence,
            "sources": page.sources,
            "related": page.related,
        }
        if page.type == "concept":
            fm.pop("kind")
        fm_yaml = yaml.safe_dump(fm, sort_keys=False, allow_unicode=True).strip()
        parts = [f"---\n{fm_yaml}\n---", "", f"# {page.title}", ""]
        if page.summary:
            parts += ["## Summary", "", page.summary.strip(), ""]
        parts += ["## Facts", ""]
        if page.facts:
            parts += [f.to_line() for f in page.facts]
        else:
            parts += ["_(no facts yet)_"]
        if page.body_extra.strip():
            parts += ["", page.body_extra.strip()]
        return "\n".join(parts) + "\n"

    def _parse(self, path: Path) -> Page:
        text = path.read_text(encoding="utf-8")
        match = _FRONTMATTER_RE.match(text)
        if not match:
            raise ValueError(f"{path} has no YAML frontmatter")
        fm = yaml.safe_load(match.group(1)) or {}
        body = match.group(2)

        facts = _parse_facts_section(body)
        summary = _parse_summary_section(body)
        body_extra = _parse_body_extra(body)

        return Page(
            id=fm.get("id") or path.stem,
            title=fm.get("title", path.stem),
            type=fm.get("type", "entity"),
            kind=fm.get("kind"),
            aliases=list(fm.get("aliases") or []),
            tags=list(fm.get("tags") or []),
            created=fm.get("created") or today_iso(),
            updated=fm.get("updated") or today_iso(),
            contributors=list(fm.get("contributors") or []),
            confidence=fm.get("confidence", "medium"),
            sources=list(fm.get("sources") or []),
            related=list(fm.get("related") or []),
            summary=summary,
            facts=facts,
            body_extra=body_extra,
        )


# ── Parsing helpers ──────────────────────────────────────────────────────────

_FACT_LINE_RE = re.compile(
    r"^- (?P<claim>.*?) "
    r"_\(source: (?P<source>[^,]+), "
    r"confidence: (?P<conf>high|medium|low), "
    r"added: (?P<added>\d{4}-\d{2}-\d{2})\)_\s*$"
)


def _parse_facts_section(body: str) -> list[Fact]:
    section = _extract_section(body, "Facts")
    if section is None:
        return []
    facts: list[Fact] = []
    for line in section.splitlines():
        m = _FACT_LINE_RE.match(line.strip())
        if not m:
            continue
        facts.append(
            Fact(
                claim=m.group("claim"),
                source=m.group("source"),
                added=m.group("added"),
                confidence=m.group("conf"),  # type: ignore[arg-type]
            )
        )
    return facts


def _parse_summary_section(body: str) -> str:
    section = _extract_section(body, "Summary")
    return (section or "").strip()


def _parse_body_extra(body: str) -> str:
    """Everything after the ## Facts section (## History, ## Open questions, etc.)."""
    lines = body.splitlines()
    try:
        start = next(i for i, line in enumerate(lines) if line.strip() == "## Facts")
    except StopIteration:
        return ""
    # Walk forward until the next `## ` heading.
    after_facts = lines[start + 1:]
    extra_start = None
    for i, line in enumerate(after_facts):
        if line.startswith("## ") and i > 0:
            extra_start = i
            break
    if extra_start is None:
        return ""
    return "\n".join(after_facts[extra_start:]).strip()


def _extract_section(body: str, heading: str) -> str | None:
    """Return the body (without heading line) of a `## {heading}` section."""
    lines = body.splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.strip() == f"## {heading}":
            start = i + 1
            break
    if start is None:
        return None
    end = len(lines)
    for i in range(start, len(lines)):
        if lines[i].startswith("## "):
            end = i
            break
    return "\n".join(lines[start:end]).strip()


def _candidate_key(cf: CandidateFact) -> str:
    return f"{cf.captured}|{cf.subject_hint}|{cf.claim[:80]}"
