"""Walk a corpus directory and load each JD as a structured ``JDEntry``."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from agentforge.corpus.models import Corpus, JDEntry, JDFrontmatter

# Pattern for a YAML frontmatter block at the very start of a file:
# ---\n<yaml>\n---\n<rest>
_FRONTMATTER_RE = re.compile(
    r"\A---\s*\n(?P<yaml>.*?)\n---\s*\n?(?P<body>.*)\Z",
    re.DOTALL,
)


def parse_frontmatter(text: str) -> tuple[JDFrontmatter | None, str]:
    """Split a markdown file into (frontmatter, body).

    Returns ``(None, text)`` when the file has no frontmatter block —
    callers can then decide whether to error or fall back to a default.
    """
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return None, text
    raw = m.group("yaml")
    body = m.group("body")
    try:
        data = yaml.safe_load(raw) or {}
    except yaml.YAMLError as e:
        raise ValueError(f"invalid YAML frontmatter: {e}") from e
    if not isinstance(data, dict):
        raise ValueError("frontmatter must be a YAML mapping at the top level")
    fm = JDFrontmatter.model_validate(data)
    return fm, body.strip() + "\n"


def _slug(name: str) -> str:
    """Filesystem-safe slug from a filename stem."""
    s = re.sub(r"[^a-z0-9_-]+", "-", name.lower()).strip("-")
    return s or "role"


def load_corpus(directory: Path) -> Corpus:
    """Load every ``*.md`` JD in ``directory`` into a Corpus.

    Files without a frontmatter block raise ``ValueError`` — the corpus
    contract is "frontmatter is required." Files with malformed YAML or
    missing required fields likewise raise.
    """
    directory = Path(directory).expanduser().resolve()
    if not directory.is_dir():
        raise FileNotFoundError(f"corpus directory not found: {directory}")

    md_files = sorted(directory.glob("*.md"))
    entries: list[JDEntry] = []
    for path in md_files:
        text = path.read_text(encoding="utf-8")
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
