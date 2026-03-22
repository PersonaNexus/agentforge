"""Parse Slack JSON exports into structured data for methodology enrichment."""
from __future__ import annotations
import json
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class SlackMessage:
    """A single Slack message."""
    user: str
    text: str
    timestamp: str = ""
    thread_ts: str = ""
    reactions: int = 0


@dataclass
class SlackThread:
    """A threaded conversation."""
    root: SlackMessage
    replies: list[SlackMessage] = field(default_factory=list)


@dataclass
class SlackCorpus:
    """Parsed Slack export data relevant to methodology extraction."""
    messages: list[SlackMessage] = field(default_factory=list)
    threads: list[SlackThread] = field(default_factory=list)
    decision_points: list[str] = field(default_factory=list)
    recurring_patterns: list[str] = field(default_factory=list)

    def to_enrichment(self) -> dict[str, str]:
        """Convert to methodology enrichment context."""
        examples = "\n\n".join(self.decision_points[:10])
        patterns = "\n".join(f"- {p}" for p in self.recurring_patterns[:5])
        return {
            "examples": examples,
            "operational_context": f"Recurring communication patterns:\n{patterns}" if patterns else "",
        }


# Decision signal keywords
_DECISION_SIGNALS = [
    "let's go with", "decided to", "the approach is", "we'll use",
    "agreed on", "final decision", "moving forward with", "conclusion:",
    "tldr:", "tl;dr:", "summary:", "action item",
]

_PATTERN_SIGNALS = [
    "as usual", "like last time", "same process", "standard procedure",
    "every time we", "whenever this", "the pattern is", "rule of thumb",
]


class SlackParser:
    """Parse Slack JSON exports for methodology enrichment."""

    def parse(
        self,
        path: Path,
        channel_filter: list[str] | None = None,
        user_filter: list[str] | None = None,
    ) -> SlackCorpus:
        """Parse a Slack export (ZIP or directory of JSON files)."""
        messages = self._load_messages(path, channel_filter)

        if user_filter:
            messages = [m for m in messages if m.user in user_filter]

        threads = self._build_threads(messages)
        decision_points = self._extract_decisions(messages)
        recurring_patterns = self._extract_patterns(messages)

        return SlackCorpus(
            messages=messages,
            threads=threads,
            decision_points=decision_points,
            recurring_patterns=recurring_patterns,
        )

    def _load_messages(
        self, path: Path, channel_filter: list[str] | None
    ) -> list[SlackMessage]:
        """Load messages from ZIP or directory."""
        messages = []

        if path.suffix == ".zip":
            messages = self._load_from_zip(path, channel_filter)
        elif path.is_dir():
            messages = self._load_from_dir(path, channel_filter)
        elif path.suffix == ".json":
            messages = self._load_json_file(path)

        return messages

    def _load_from_zip(
        self, zip_path: Path, channel_filter: list[str] | None
    ) -> list[SlackMessage]:
        messages = []
        with zipfile.ZipFile(zip_path) as zf:
            for name in zf.namelist():
                if not name.endswith(".json"):
                    continue
                # Channel is the directory name
                parts = name.split("/")
                if len(parts) >= 2 and channel_filter:
                    channel = parts[-2]
                    if channel not in channel_filter:
                        continue
                try:
                    data = json.loads(zf.read(name))
                    if isinstance(data, list):
                        messages.extend(self._parse_messages(data))
                except (json.JSONDecodeError, KeyError):
                    continue
        return messages

    def _load_from_dir(
        self, dir_path: Path, channel_filter: list[str] | None
    ) -> list[SlackMessage]:
        messages = []
        for json_file in dir_path.rglob("*.json"):
            if channel_filter:
                channel = json_file.parent.name
                if channel not in channel_filter:
                    continue
            messages.extend(self._load_json_file(json_file))
        return messages

    def _load_json_file(self, path: Path) -> list[SlackMessage]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return self._parse_messages(data)
        except (json.JSONDecodeError, OSError):
            pass
        return []

    def _parse_messages(self, data: list) -> list[SlackMessage]:
        messages = []
        for item in data:
            if not isinstance(item, dict):
                continue
            text = item.get("text", "")
            if not text or len(text) < 10:
                continue
            reactions = sum(
                r.get("count", 0) for r in item.get("reactions", [])
            )
            messages.append(SlackMessage(
                user=item.get("user", "unknown"),
                text=text,
                timestamp=item.get("ts", ""),
                thread_ts=item.get("thread_ts", ""),
                reactions=reactions,
            ))
        return messages

    def _build_threads(self, messages: list[SlackMessage]) -> list[SlackThread]:
        thread_map: dict[str, list[SlackMessage]] = {}
        roots: dict[str, SlackMessage] = {}

        for msg in messages:
            ts = msg.thread_ts or msg.timestamp
            if not ts:
                continue
            if msg.timestamp == ts:
                roots[ts] = msg
            else:
                thread_map.setdefault(ts, []).append(msg)

        threads = []
        for ts, root in roots.items():
            replies = thread_map.get(ts, [])
            if replies:
                threads.append(SlackThread(root=root, replies=replies))

        return threads

    def _extract_decisions(self, messages: list[SlackMessage]) -> list[str]:
        decisions = []
        for msg in messages:
            text_lower = msg.text.lower()
            if any(signal in text_lower for signal in _DECISION_SIGNALS):
                decisions.append(msg.text[:500])
        # Also include highly-reacted messages
        high_reaction = sorted(messages, key=lambda m: m.reactions, reverse=True)
        for msg in high_reaction[:5]:
            if msg.reactions >= 3 and msg.text not in decisions:
                decisions.append(msg.text[:500])
        return decisions[:20]

    def _extract_patterns(self, messages: list[SlackMessage]) -> list[str]:
        patterns = []
        for msg in messages:
            text_lower = msg.text.lower()
            if any(signal in text_lower for signal in _PATTERN_SIGNALS):
                # Extract the sentence containing the pattern signal
                patterns.append(msg.text[:300])
        return patterns[:10]
