"""JD corpus — shared input layer for ``department`` and (later) ``market``.

A corpus is a directory of ``*.md`` files, each with a YAML frontmatter
header describing the role plus a markdown body that is the actual JD
text. Loaders here parse the frontmatter, validate it, and return
structured ``JDEntry`` objects ready for downstream extraction.

Designed to be the single canonical input shape across AgentForge's
multi-JD features. Per-JD extraction results are cached so repeated
operations on the same corpus don't re-call the LLM.
"""

from agentforge.corpus.loader import load_corpus, parse_frontmatter
from agentforge.corpus.models import Corpus, JDEntry, JDFrontmatter

__all__ = [
    "Corpus",
    "JDEntry",
    "JDFrontmatter",
    "load_corpus",
    "parse_frontmatter",
]
