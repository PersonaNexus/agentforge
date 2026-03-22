"""Parse runbook/SOP documents for methodology enrichment."""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Procedure:
    """A step-by-step procedure from a runbook."""
    name: str
    steps: str
    trigger: str = ""

    def to_dict(self) -> dict:
        return {"name": self.name, "steps": self.steps, "trigger": self.trigger}


@dataclass
class RunbookCorpus:
    """Parsed runbook data for methodology enrichment."""
    procedures: list[Procedure] = field(default_factory=list)
    decision_trees: list[str] = field(default_factory=list)
    checklists: list[list[str]] = field(default_factory=list)
    templates: list[str] = field(default_factory=list)

    def to_enrichment(self) -> dict[str, str]:
        """Convert to methodology enrichment context."""
        frameworks = []
        for proc in self.procedures[:5]:
            frameworks.append(f"Procedure: {proc.name}\n{proc.steps}")

        examples = list(self.templates[:5])
        for checklist in self.checklists[:3]:
            examples.append("Checklist:\n" + "\n".join(f"- {item}" for item in checklist))

        return {
            "frameworks": "\n\n".join(frameworks),
            "examples": "\n\n".join(examples),
        }


class RunbookParser:
    """Parse runbook/SOP markdown documents."""

    def parse(self, path: Path) -> RunbookCorpus:
        """Parse a runbook file (markdown or plain text)."""
        text = path.read_text(encoding="utf-8")
        sections = self._split_sections(text)

        procedures = self._extract_procedures(sections)
        decision_trees = self._extract_decision_trees(text)
        checklists = self._extract_checklists(text)
        templates = self._extract_templates(sections)

        return RunbookCorpus(
            procedures=procedures,
            decision_trees=decision_trees,
            checklists=checklists,
            templates=templates,
        )

    def _split_sections(self, text: str) -> list[tuple[str, str]]:
        """Split markdown into (heading, content) pairs."""
        sections = []
        heading_pattern = re.compile(r"^(#{1,4})\s+(.+)$", re.MULTILINE)
        matches = list(heading_pattern.finditer(text))

        for i, match in enumerate(matches):
            heading = match.group(2).strip()
            start = match.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            content = text[start:end].strip()
            sections.append((heading, content))

        if not sections and text.strip():
            sections.append(("Document", text.strip()))

        return sections

    def _extract_procedures(self, sections: list[tuple[str, str]]) -> list[Procedure]:
        """Extract step-by-step procedures."""
        procedures = []
        procedure_keywords = [
            "procedure", "process", "steps", "how to", "runbook",
            "playbook", "workflow", "instructions", "guide",
        ]

        for heading, content in sections:
            heading_lower = heading.lower()
            is_procedure = any(kw in heading_lower for kw in procedure_keywords)

            # Also detect numbered lists as procedures
            numbered_steps = re.findall(r"^\s*\d+[\.\)]\s+.+", content, re.MULTILINE)
            if is_procedure or len(numbered_steps) >= 3:
                trigger = ""
                # Look for trigger phrases
                for line in content.splitlines()[:3]:
                    if any(kw in line.lower() for kw in ["when", "if", "trigger", "alert"]):
                        trigger = line.strip()
                        break

                procedures.append(Procedure(
                    name=heading,
                    steps=content[:1000],
                    trigger=trigger,
                ))

        return procedures

    def _extract_decision_trees(self, text: str) -> list[str]:
        """Extract if/then/else blocks."""
        trees = []
        # Look for if/then patterns
        pattern = re.compile(
            r"(?:^|\n)\s*(?:if|when)\s+.+?(?:then|:)\s*\n(?:.*\n)*?(?:\s*(?:else|otherwise|if not)\s+.+)?",
            re.IGNORECASE | re.MULTILINE,
        )
        for match in pattern.finditer(text):
            tree = match.group().strip()
            if len(tree) > 30:
                trees.append(tree[:500])
        return trees[:10]

    def _extract_checklists(self, text: str) -> list[list[str]]:
        """Extract checkbox or bullet checklists."""
        checklists = []
        current: list[str] = []

        for line in text.splitlines():
            # Match checkbox items: - [ ] or - [x] or simple bullets in checklist context
            if re.match(r"^\s*[-*]\s*\[[ xX]\]\s+", line):
                item = re.sub(r"^\s*[-*]\s*\[[ xX]\]\s+", "", line).strip()
                current.append(item)
            else:
                if len(current) >= 2:
                    checklists.append(current)
                current = []

        if len(current) >= 2:
            checklists.append(current)

        return checklists

    def _extract_templates(self, sections: list[tuple[str, str]]) -> list[str]:
        """Extract template/format sections."""
        templates = []
        template_keywords = ["template", "format", "example", "sample", "output"]

        for heading, content in sections:
            if any(kw in heading.lower() for kw in template_keywords):
                templates.append(f"## {heading}\n\n{content[:500]}")

        # Also extract fenced code blocks as potential templates
        code_blocks = re.findall(r"```[\s\S]*?```", "\n".join(c for _, c in sections))
        for block in code_blocks[:3]:
            if len(block) > 50:
                templates.append(block)

        return templates[:10]
