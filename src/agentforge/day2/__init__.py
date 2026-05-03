"""Shared infrastructure for AgentForge's day-2+ products (Tend, Drill, Department, Market).

Each day-2+ product follows the same operating model: observe → diagnose →
propose → test → version. They share enough machinery — git state probes,
JSONL evolution logs, frontmatter parsing, finding-list markdown rendering,
CLI directory validation — that we factor it here once instead of mirroring
the same code across each product.

This package is intentionally small and dependency-light. No LLM, no
filesystem writes outside the helpers' explicit jobs, no opinionated
data shapes — products supply their own pydantic models and pass them
to the shared renderers/loaders.
"""

from agentforge.day2.cli_validators import validate_dir
from agentforge.day2.frontmatter import (
    FRONTMATTER_RE,
    FrontmatterParseError,
    split_frontmatter,
)
from agentforge.day2.finding_render import (
    SeverityCounts,
    count_severities,
    render_findings_markdown,
)
from agentforge.day2.safe_io import (
    DEFAULT_MAX_INGEST_BYTES,
    FileTooLargeError,
    read_text_capped,
    walk_files_no_symlinks,
)
from agentforge.day2.vcs import git_state, try_rev_parse
from agentforge.day2.version_log import (
    annotate_latest as annotate_latest_version,
    commit_label,
    load_versions as load_jsonl_versions,
    render_version_log,
)

__all__ = [
    "DEFAULT_MAX_INGEST_BYTES",
    "FRONTMATTER_RE",
    "FileTooLargeError",
    "FrontmatterParseError",
    "SeverityCounts",
    "annotate_latest_version",
    "commit_label",
    "count_severities",
    "git_state",
    "load_jsonl_versions",
    "read_text_capped",
    "render_findings_markdown",
    "render_version_log",
    "split_frontmatter",
    "try_rev_parse",
    "validate_dir",
    "walk_files_no_symlinks",
]
