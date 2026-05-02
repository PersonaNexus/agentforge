"""Tend CLI — sub-app registered under ``agentforge tend ...``."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from agentforge.tend.ab import (
    auto_scenario_set,
    list_scenario_sets,
    load_scenarios,
    run_ab,
    write_ab_report,
)
from agentforge.tend.ingest import ingest, write_snapshot
from agentforge.tend.models import PersonaSnapshot, snapshot_path
from agentforge.tend.version import (
    annotate_latest,
    load_versions,
    record_if_changed,
    render_log,
)
from agentforge.tend.watch import (
    list_snapshots,
    render_report_markdown,
    watch,
    write_report,
)

app = typer.Typer(
    name="tend",
    help="Day-2+ persona maintenance: ingest, watch, ab, version.",
    no_args_is_help=True,
)
console = Console()


def _summarize_snapshot(s: PersonaSnapshot) -> None:
    header = (
        f"[bold]{s.agent_name}[/bold]  "
        f"[dim]captured {s.captured_at.isoformat(timespec='seconds')}[/dim]"
    )
    console.print(Panel(header, border_style="cyan"))

    counts = Table(show_header=False, box=None, pad_edge=False)
    counts.add_column(style="dim")
    counts.add_column(style="bold")
    counts.add_row("SOUL sections", str(len(s.soul_sections)))
    counts.add_row("SOUL principles", str(len(s.soul_principles)))
    counts.add_row("SOUL guardrails", str(len(s.soul_guardrails)))
    counts.add_row("YAML principles", str(len(s.yaml_principles)))
    counts.add_row("YAML guardrails", str(len(s.yaml_guardrails)))
    counts.add_row("Persona artifacts", str(len(s.artifacts)))
    counts.add_row("Memory signals (7d)", str(len(s.memory_signals)))
    if s.voice:
        counts.add_row("Voice words", str(s.voice.word_count))
        counts.add_row("Voice avg sent. len", f"{s.voice.avg_sentence_length:.1f}")
        counts.add_row("Voice question rate", f"{s.voice.question_rate:.1%}")
    console.print(counts)

    if s.artifacts:
        art = Table(title="Persona artifacts", show_lines=False)
        art.add_column("Path", style="cyan")
        art.add_column("Lines", justify="right")
        art.add_column("SHA-256 (head)", style="dim")
        for a in s.artifacts:
            art.add_row(a.path, str(a.line_count), a.sha256[:12])
        console.print(art)

    if s.notes:
        console.print(Panel("\n".join(f"• {n}" for n in s.notes), title="Notes",
                            border_style="yellow"))


@app.command("ingest")
def cmd_ingest(
    agent_dir: Path = typer.Argument(
        ...,
        help="Path to the agent directory (e.g. ~/personal-ai-org/agents/axiom).",
    ),
    output: Path | None = typer.Option(
        None,
        "--output", "-o",
        help="Write snapshot here instead of <agent>/.tend/snapshots/.",
    ),
    json_only: bool = typer.Option(
        False,
        "--json",
        help="Print snapshot JSON to stdout, skip the rich summary.",
    ),
) -> None:
    """Read an agent's persona artifacts and write a PersonaSnapshot."""
    agent_dir = agent_dir.expanduser().resolve()
    snapshot = ingest(agent_dir)

    out_path = output or snapshot_path(agent_dir, snapshot.captured_at)
    write_snapshot(snapshot, out_path)

    new_version = record_if_changed(agent_dir, snapshot, out_path)

    if json_only:
        typer.echo(snapshot.model_dump_json(indent=2))
        return

    _summarize_snapshot(snapshot)
    console.print(
        f"\n[green]✓[/green] snapshot written to "
        f"[bold]{out_path}[/bold]"
    )
    if new_version is not None:
        prior_count = len(load_versions(agent_dir)) - 1
        console.print(
            f"[green]✓[/green] SOUL version recorded — "
            f"v{prior_count + 1} ([dim]{new_version.summary or '—'}[/dim])"
        )


@app.command("show")
def cmd_show(
    snapshot_file: Path = typer.Argument(..., help="Path to a snapshot JSON file."),
) -> None:
    """Pretty-print an existing snapshot file."""
    data = json.loads(snapshot_file.read_text(encoding="utf-8"))
    s = PersonaSnapshot.model_validate(data)
    _summarize_snapshot(s)


@app.command("watch")
def cmd_watch(
    agent_dir: Path = typer.Argument(
        ...,
        help="Path to the agent directory.",
    ),
    write: bool = typer.Option(
        True,
        "--write/--no-write",
        help="Write the markdown report to <agent>/.tend/watch-<date>.md.",
    ),
) -> None:
    """Diff the two most recent snapshots and surface findings."""
    agent_dir = agent_dir.expanduser().resolve()
    report = watch(agent_dir)
    md = render_report_markdown(report)
    typer.echo(md)
    if write:
        out = write_report(report, agent_dir)
        console.print(f"[green]✓[/green] report written to [bold]{out}[/bold]")


@app.command("snapshots")
def cmd_snapshots(
    agent_dir: Path = typer.Argument(..., help="Path to the agent directory."),
) -> None:
    """List snapshots for an agent, oldest → newest."""
    agent_dir = agent_dir.expanduser().resolve()
    snaps = list_snapshots(agent_dir)
    if not snaps:
        console.print(f"[dim]no snapshots under {agent_dir}/.tend/snapshots/[/dim]")
        return
    table = Table(title=f"{agent_dir.name} snapshots", show_lines=False)
    table.add_column("File", style="cyan")
    table.add_column("Size", justify="right")
    for s in snaps:
        table.add_row(s.name, f"{s.stat().st_size:,} B")
    console.print(table)


@app.command("ab")
def cmd_ab(
    agent_dir: Path = typer.Argument(..., help="Path to the agent directory."),
    variant: Path = typer.Option(
        ...,
        "--variant", "-v",
        help="Path to the proposed variant SOUL.md to compare against.",
    ),
    scenarios: str = typer.Option(
        "auto",
        "--scenarios", "-s",
        help="Scenario set name (e.g. 'default', 'axiom') or path to a JSON file. "
             "'auto' picks the agent-named set if one exists, else 'default'.",
    ),
    model: str | None = typer.Option(
        None, "--model", "-m",
        help="LLM model to use for both response generation and judging.",
    ),
    response_max_tokens: int = typer.Option(
        800, "--response-max-tokens",
        help="Max tokens per persona response generation.",
    ),
) -> None:
    """A/B compare a current SOUL vs a proposed variant on scenarios."""
    agent_dir = agent_dir.expanduser().resolve()
    variant = variant.expanduser().resolve()
    soul_path = agent_dir / "SOUL.md"
    if not soul_path.is_file():
        console.print(f"[red]error: {soul_path} not found[/red]")
        raise typer.Exit(code=1)
    if not variant.is_file():
        console.print(f"[red]error: variant {variant} not found[/red]")
        raise typer.Exit(code=1)

    set_name = scenarios
    if set_name == "auto":
        set_name = auto_scenario_set(agent_dir.name)
        console.print(f"[dim]auto-selected scenario set:[/dim] [bold]{set_name}[/bold]")
    scenario_set = load_scenarios(set_name)

    from agentforge.llm.client import LLMClient
    client = LLMClient(model=model) if model else LLMClient()
    model_label = client.model

    console.print(
        f"[cyan]running A/B[/cyan] · {len(scenario_set.scenarios)} scenarios · "
        f"model=[bold]{model_label}[/bold]"
    )

    control_soul = soul_path.read_text(encoding="utf-8")
    treatment_soul = variant.read_text(encoding="utf-8")

    report = run_ab(
        agent_name=agent_dir.name,
        control_soul=control_soul,
        treatment_soul=treatment_soul,
        scenarios=scenario_set,
        client=client,
        response_max_tokens=response_max_tokens,
        control_soul_path=str(soul_path),
        treatment_soul_path=str(variant),
        model_label=model_label,
    )
    out_path = write_ab_report(report, agent_dir)
    agg = report.aggregate()
    if agg:
        console.print(
            f"\n[green]✓[/green] A/B complete · "
            f"control={agg['control_avg_total']} · "
            f"treatment={agg['treatment_avg_total']} · "
            f"delta={agg['delta']:+.2f}"
        )
    console.print(f"  report: [bold]{out_path}[/bold]")


@app.command("scenarios")
def cmd_scenarios() -> None:
    """List bundled scenario sets."""
    sets = list_scenario_sets()
    if not sets:
        console.print("[dim]no bundled scenario sets[/dim]")
        return
    table = Table(title="Scenario sets", show_lines=False)
    table.add_column("Name", style="cyan")
    table.add_column("# Scenarios", justify="right")
    table.add_column("Description", style="dim")
    for name in sets:
        s = load_scenarios(name)
        table.add_row(s.name, str(len(s.scenarios)), s.description[:80])
    console.print(table)


version_app = typer.Typer(
    name="version",
    help="SOUL version log — see how an agent's persona has evolved over time.",
    no_args_is_help=True,
)


@version_app.command("log")
def cmd_version_log(
    agent_dir: Path = typer.Argument(..., help="Path to the agent directory."),
) -> None:
    """Show the SOUL version log for an agent."""
    agent_dir = agent_dir.expanduser().resolve()
    entries = load_versions(agent_dir)
    typer.echo(render_log(entries))


@version_app.command("note")
def cmd_version_note(
    agent_dir: Path = typer.Argument(..., help="Path to the agent directory."),
    note: str = typer.Argument(..., help="Free-form note to attach to the latest version."),
) -> None:
    """Attach a note to the most recent SOUL version entry."""
    agent_dir = agent_dir.expanduser().resolve()
    entry = annotate_latest(agent_dir, note)
    if entry is None:
        console.print("[yellow]no version entries yet — run `tend ingest` first[/yellow]")
        raise typer.Exit(code=1)
    console.print(f"[green]✓[/green] note attached to sha {entry.soul_sha256[:12]}")


app.add_typer(version_app, name="version")


def register(parent: typer.Typer) -> None:
    """Register tend as a sub-app on the main agentforge CLI."""
    parent.add_typer(app, name="tend")
