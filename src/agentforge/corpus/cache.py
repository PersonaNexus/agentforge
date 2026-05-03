"""Cache extraction results keyed on JD body sha256.

The corpus is read repeatedly by every higher-level command (department,
market). Re-running forge extraction on every JD per command is wasteful
and slow. We cache results under ``<corpus>/.agentforge/extractions/``
keyed by the sha256 of the JD body — invalidates automatically when a JD
is edited.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from agentforge.corpus.models import JDEntry


def _cache_dir(corpus_root: Path) -> Path:
    return corpus_root / ".agentforge" / "extractions"


def _key(entry: JDEntry) -> str:
    h = hashlib.sha256()
    h.update(entry.body.encode("utf-8"))
    return h.hexdigest()[:16]


def cache_path(corpus_root: Path, entry: JDEntry) -> Path:
    return _cache_dir(corpus_root) / f"{entry.role_id}-{_key(entry)}.json"


def load(corpus_root: Path, entry: JDEntry) -> dict | None:
    p = cache_path(corpus_root, entry)
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def save(corpus_root: Path, entry: JDEntry, payload: dict) -> Path:
    p = cache_path(corpus_root, entry)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return p


def clear(corpus_root: Path) -> int:
    """Remove every cached extraction. Returns number of files removed."""
    d = _cache_dir(corpus_root)
    if not d.is_dir():
        return 0
    n = 0
    for f in d.glob("*.json"):
        try:
            f.unlink()
            n += 1
        except OSError:
            pass
    return n
