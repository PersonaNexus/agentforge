"""Multi-source ingestion: combine JD with supplementary sources."""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class MethodologyEnrichment:
    """Compiled enrichment data from all supplementary sources."""
    examples: str = ""
    frameworks: str = ""
    operational_context: str = ""

    def has_content(self) -> bool:
        return bool(self.examples.strip() or self.frameworks.strip() or self.operational_context.strip())


@dataclass
class SupplementarySource:
    """A supplementary data source for enrichment."""
    path: str
    source_type: str  # slack, git, runbook, meeting_notes, auto
    options: dict = field(default_factory=dict)  # Parser-specific options


def detect_source_type(path: Path) -> str:
    """Auto-detect the type of a supplementary source."""
    suffix = path.suffix.lower()
    name = path.name.lower()

    if suffix == ".zip":
        return "slack"
    if "runbook" in name or "sop" in name or "playbook" in name:
        return "runbook"
    if "meeting" in name or "notes" in name or "transcript" in name:
        return "meeting_notes"
    if suffix in (".md", ".txt", ".markdown"):
        # Try to detect by content
        try:
            content = path.read_text(encoding="utf-8")[:500].lower()
            if "action item" in content or "attendees" in content or "agenda" in content:
                return "meeting_notes"
            if "procedure" in content or "step 1" in content or "checklist" in content:
                return "runbook"
        except OSError:
            pass
        return "runbook"  # Default for text files
    if suffix == ".json":
        return "slack"

    return "runbook"  # Fallback


def parse_supplementary_source(source: SupplementarySource) -> Any:
    """Parse a single supplementary source and return a corpus."""
    path = Path(source.path)
    source_type = source.source_type

    if source_type == "auto":
        source_type = detect_source_type(path)

    if source_type == "slack":
        from agentforge.ingestion.slack import SlackParser
        parser = SlackParser()
        return parser.parse(
            path,
            channel_filter=source.options.get("channel_filter"),
            user_filter=source.options.get("user_filter"),
        )

    elif source_type == "git":
        from agentforge.ingestion.git_log import GitLogParser
        parser = GitLogParser()
        if path.is_dir():
            return parser.parse(
                repo_path=path,
                author_filter=source.options.get("author_filter"),
                since=source.options.get("since"),
            )
        else:
            return parser.parse(log_text=path.read_text(encoding="utf-8"))

    elif source_type == "meeting_notes":
        from agentforge.ingestion.meeting_notes import MeetingNotesParser
        parser = MeetingNotesParser()
        return parser.parse(path)

    else:  # runbook
        from agentforge.ingestion.runbook import RunbookParser
        parser = RunbookParser()
        return parser.parse(path)


def compile_enrichment(corpora: list[Any]) -> MethodologyEnrichment:
    """Compile enrichment data from all parsed corpora."""
    all_examples = []
    all_frameworks = []
    all_operational = []

    for corpus in corpora:
        enrichment = corpus.to_enrichment()
        if enrichment.get("examples"):
            all_examples.append(enrichment["examples"])
        if enrichment.get("frameworks"):
            all_frameworks.append(enrichment["frameworks"])
        if enrichment.get("operational_context"):
            all_operational.append(enrichment["operational_context"])

    return MethodologyEnrichment(
        examples="\n\n---\n\n".join(all_examples),
        frameworks="\n\n---\n\n".join(all_frameworks),
        operational_context="\n\n---\n\n".join(all_operational),
    )
