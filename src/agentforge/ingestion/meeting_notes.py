"""Parse meeting notes/transcripts for methodology enrichment."""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class MeetingCorpus:
    """Parsed meeting notes data for methodology enrichment."""
    decisions: list[str] = field(default_factory=list)
    action_items: list[str] = field(default_factory=list)
    recurring_topics: list[str] = field(default_factory=list)
    stakeholder_patterns: list[str] = field(default_factory=list)

    def to_enrichment(self) -> dict[str, str]:
        """Convert to methodology enrichment context."""
        frameworks = "\n".join(f"- Decision: {d}" for d in self.decisions[:10])
        operational = []
        if self.action_items:
            operational.append(
                "Common action items:\n" + "\n".join(f"- {a}" for a in self.action_items[:5])
            )
        if self.stakeholder_patterns:
            operational.append(
                "Stakeholder communication:\n" + "\n".join(f"- {s}" for s in self.stakeholder_patterns[:5])
            )
        return {
            "frameworks": frameworks,
            "operational_context": "\n\n".join(operational),
        }


class MeetingNotesParser:
    """Parse meeting notes and transcripts."""

    def parse(self, path: Path) -> MeetingCorpus:
        """Parse meeting notes from a markdown/text file."""
        text = path.read_text(encoding="utf-8")

        return MeetingCorpus(
            decisions=self._extract_decisions(text),
            action_items=self._extract_action_items(text),
            recurring_topics=self._extract_topics(text),
            stakeholder_patterns=self._extract_stakeholders(text),
        )

    def _extract_decisions(self, text: str) -> list[str]:
        """Extract decision statements."""
        decisions = []
        decision_patterns = [
            r"(?:decided|agreed|decision|resolved|concluded|approved)[\s:]+(.+?)(?:\n|$)",
            r"(?:^|\n)\s*>\s*(.+?(?:decided|agreed|will|approved).+?)(?:\n|$)",
        ]
        for pattern in decision_patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE | re.MULTILINE):
                decision = match.group(1).strip()
                if len(decision) > 15:
                    decisions.append(decision[:300])
        return list(dict.fromkeys(decisions))[:15]

    def _extract_action_items(self, text: str) -> list[str]:
        """Extract action items and TODOs."""
        items = []
        patterns = [
            r"(?:TODO|Action|AI|Action Item|Task)[\s:]+(.+?)(?:\n|$)",
            r"[-*]\s*\[[ ]\]\s+(.+?)(?:\n|$)",  # Unchecked checkboxes
            r"@\w+\s+(?:to|will|should)\s+(.+?)(?:\n|$)",
        ]
        for pattern in patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE | re.MULTILINE):
                item = match.group(1).strip()
                if len(item) > 10:
                    items.append(item[:200])
        return list(dict.fromkeys(items))[:15]

    def _extract_topics(self, text: str) -> list[str]:
        """Extract topic headings as recurring discussion areas."""
        topics = []
        # Look for agenda items or section headings
        heading_pattern = re.compile(r"^#{1,3}\s+(.+)$", re.MULTILINE)
        for match in heading_pattern.finditer(text):
            topic = match.group(1).strip()
            # Skip generic headings
            if topic.lower() not in {"notes", "meeting notes", "agenda", "attendees", "date"}:
                topics.append(topic)
        return topics[:10]

    def _extract_stakeholders(self, text: str) -> list[str]:
        """Extract stakeholder communication patterns."""
        patterns = []
        # Look for @mentions or named assignments
        mention_pattern = re.compile(r"@(\w+)\s+(.{10,80}?)(?:\n|$)")
        for match in mention_pattern.finditer(text):
            patterns.append(f"{match.group(1)}: {match.group(2).strip()}")

        # Look for role-based patterns
        role_pattern = re.compile(
            r"(?:from|with|for|to)\s+(the\s+)?(team|engineering|product|design|sales|marketing|leadership)\s+(.{10,80}?)(?:\n|$)",
            re.IGNORECASE,
        )
        for match in role_pattern.finditer(text):
            patterns.append(f"{match.group(2)}: {match.group(3).strip()}")

        return list(dict.fromkeys(patterns))[:10]
