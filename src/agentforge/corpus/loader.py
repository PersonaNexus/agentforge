"""Walk a corpus directory and load each JD as a structured ``JDEntry``."""

from __future__ import annotations

import re
from pathlib import Path

from agentforge.corpus.models import Corpus, JDEntry, JDFrontmatter
from agentforge.day2.frontmatter import (
    FRONTMATTER_RE as _FRONTMATTER_RE,
    FrontmatterParseError,
    split_frontmatter,
)
from agentforge.day2.safe_io import read_text_capped


def parse_frontmatter(text: str) -> tuple[JDFrontmatter | None, str]:
    """Split a markdown file into (frontmatter, body).

    Returns ``(None, text)`` when the file has no frontmatter block.
    Raises ``ValueError`` on malformed YAML or non-mapping content
    (corpus's strict contract).
    """
    if not _FRONTMATTER_RE.match(text):
        return None, text
    try:
        data, body, _ = split_frontmatter(text, strict=True)
    except FrontmatterParseError as e:
        raise ValueError(str(e)) from e
    fm = JDFrontmatter.model_validate(data)
    return fm, body.strip() + "\n"


def _slug(name: str) -> str:
    """Filesystem-safe slug from a filename stem."""
    s = re.sub(r"[^a-z0-9_-]+", "-", name.lower()).strip("-")
    return s or "role"


def load_corpus(directory: Path) -> Corpus:
    """Load every ``*.md`` JD in ``directory`` into a Corpus."""
    directory = Path(directory).expanduser().resolve()
    if not directory.is_dir():
        raise FileNotFoundError(f"corpus directory not found: {directory}")

    md_files = sorted(directory.glob("*.md"))
    entries: list[JDEntry] = []
    for path in md_files:
        text = read_text_capped(path)
        fm, body = parse_frontmatter(text)
        if fm is None:
            raise ValueError(
                f"{path.name}: missing YAML frontmatter block "
                f"(expected '---' header). Add at least a 'title:' field."
            )
        entries.append(JDEntry(
            path=str(path),
            role_id=_slug(path.stem),
            frontmatter=fm,
            body=body,
        ))

    return Corpus(root=str(directory), entries=entries)
