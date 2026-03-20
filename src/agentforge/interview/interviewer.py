"""Interview mode — structured role description builder.

Asks structured questions to build a precise role description
interactively before forging. Captures purpose, common tasks,
output format preferences, and hard boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import typer
from rich.console import Console
from rich.panel import Panel

console = Console()


@dataclass
class InterviewResult:
    """Structured output from an interview session."""

    purpose: str = ""
    common_tasks: list[str] = field(default_factory=list)
    never_do: list[str] = field(default_factory=list)
    output_preferences: str = ""
    audience: str = ""
    domain: str = ""
    seniority: str = "mid"
    additional_context: str = ""

    def to_role_description(self) -> str:
        """Convert interview answers to a role description text."""
        lines: list[str] = []

        lines.append(f"# Role Description")
        lines.append("")
        lines.append(f"## Purpose")
        lines.append(self.purpose)
        lines.append("")

        if self.domain:
            lines.append(f"## Domain")
            lines.append(self.domain)
            lines.append("")

        if self.seniority:
            lines.append(f"## Seniority Level")
            lines.append(self.seniority)
            lines.append("")

        if self.common_tasks:
            lines.append("## Core Responsibilities")
            for task in self.common_tasks:
                lines.append(f"- {task}")
            lines.append("")

        if self.audience:
            lines.append("## Target Audience")
            lines.append(self.audience)
            lines.append("")

        if self.output_preferences:
            lines.append("## Output Preferences")
            lines.append(self.output_preferences)
            lines.append("")

        if self.never_do:
            lines.append("## Hard Boundaries")
            lines.append("This agent should NEVER:")
            for boundary in self.never_do:
                lines.append(f"- {boundary}")
            lines.append("")

        if self.additional_context:
            lines.append("## Additional Context")
            lines.append(self.additional_context)
            lines.append("")

        return "\n".join(lines)


class AgentInterviewer:
    """Conducts a structured interview to build a role description."""

    def interview(self) -> InterviewResult:
        """Run the interactive interview and return structured results."""
        result = InterviewResult()

        console.print(Panel(
            "[bold]Agent Interview[/bold]\n"
            "Answer the following questions to build a precise role description.\n"
            "Press Enter to skip any question.",
            border_style="blue",
        ))

        # Purpose
        result.purpose = typer.prompt(
            "\nWhat is this agent's primary job in one sentence?",
            default="",
        ).strip()

        if not result.purpose:
            console.print("[red]Purpose is required.[/red]")
            result.purpose = typer.prompt("What is this agent's primary job?")

        # Domain
        result.domain = typer.prompt(
            "What domain does this agent operate in? (e.g., data engineering, marketing, finance)",
            default="general",
        ).strip()

        # Seniority
        seniority_options = ["junior", "mid", "senior", "lead", "executive"]
        console.print("\nSeniority level:")
        for i, level in enumerate(seniority_options, 1):
            console.print(f"  [cyan]{i}[/cyan]. {level}")
        raw = typer.prompt("Selection", default="3")
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(seniority_options):
                result.seniority = seniority_options[idx]
        except ValueError:
            result.seniority = "mid"

        # Common tasks
        console.print(
            "\nWhat are the 3 most common tasks it will handle?"
            "\n  (Enter each task on a separate prompt. Leave blank to finish.)"
        )
        for i in range(10):
            task = typer.prompt(f"  Task {i + 1}", default="").strip()
            if not task:
                break
            result.common_tasks.append(task)

        # Audience
        result.audience = typer.prompt(
            "\nWho will interact with this agent? (e.g., developers, customers, analysts)",
            default="",
        ).strip()

        # Output preferences
        result.output_preferences = typer.prompt(
            "What format should outputs be in? (e.g., markdown reports, JSON, brief summaries)",
            default="",
        ).strip()

        # Hard boundaries
        console.print(
            "\nWhat should this agent NEVER do?"
            "\n  (Enter each boundary. Leave blank to finish.)"
        )
        for i in range(10):
            boundary = typer.prompt(f"  Boundary {i + 1}", default="").strip()
            if not boundary:
                break
            result.never_do.append(boundary)

        # Additional context
        result.additional_context = typer.prompt(
            "\nAnything else to know about this agent? (optional)",
            default="",
        ).strip()

        # Show summary
        console.print(Panel(
            result.to_role_description(),
            title="Generated Role Description",
            border_style="green",
        ))

        return result
