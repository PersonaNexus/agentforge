"""Shared YAML-frontmatter parsing for Drill and Corpus.

Both day-2+ products parse markdown files with ``---\\n<yaml>\\n---\\n<body>``
headers. Drill is permissive — bad YAML becomes a note on the digest;
Corpus is strict — bad YAML aborts ingestion. This module exposes both
behaviors via a ``strict`` flag.
"""

from __future__ import annotations

import re

import yaml


FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?(.*)\Z", re.DOTALL)


class FrontmatterParseError(ValueError):
    """Raised when ``strict=True`` and the YAML frontmatter fails to parse."""


def split_frontmatter(text: str, *, strict: bool = False) -> tuple[dict, str, list[str]]:
    """Split a markdown document into (frontmatter_dict, body, notes).

    Returns ``({}, text, [])`` when no frontmatter is present.

    With ``strict=False`` (Drill's mode), YAML parse failures land in
    ``notes`` and the frontmatter is silently empty. With ``strict=True``
    (Corpus's mode), parse failures raise ``FrontmatterParseError``.
    """
    notes: list[str] = []
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}, text, notes
    raw = m.group(1)
    body = m.group(2)
    try:
        fm = yaml.safe_load(raw) or {}
    except yaml.YAMLError as exc:
        if strict:
            raise FrontmatterParseError(f"frontmatter YAML parse failed: {exc}") from exc
        notes.append(f"frontmatter YAML parse failed: {exc}")
        fm = {}
    if not isinstance(fm, dict):
        if strict:
            raise FrontmatterParseError("frontmatter is not a YAML mapping")
        notes.append("frontmatter is not a mapping; ignored")
        fm = {}
    return fm, body, notes
