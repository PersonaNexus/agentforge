"""``agentforge drill ...`` sub-CLI (Phase 1.0)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from agentforge.day2.cli_validators import validate_dir
from agentforge.drill import ingest as ingest_mod
from agentforge.drill import scan as scan_mod
from agentforge.drill import version as version_mod
from agentforge.drill import watch as watch_mod
from agentforge.drill.models import SkillInventory, snapshot_path

app = typer.Typer(
    name="drill",
    help="Day-2+ skill maintenance: ingest, scan, watch, version skill folders.",
    no_args_is_help=True,
)
console = Console()


def _validate_skill_dir(skill_dir: Path) -> Path:
    return validate_dir(skill_dir, entity="skill-dir")


def _write_snapshot(inventory: SkillInventory, skill_dir: Path) -> Path:
    path = snapshot_path(skill_dir, inventory.captured_at)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(inventory.model_dump_json(indent=2), encoding="utf-8")
    return path


@app.command("ingest")
def cmd_ingest(
    skill_dir: Path = typer.Argument(
        ...,
        help="Skill folder (with SKILL.md) or parent of multiple skill folders.",
    ),
    record_version: bool = typer.Option(
        True, "--record-version/--no-record-version",
        help="Append to versions.jsonl when the inventory fingerprint changes.",
    ),
) -> None:
    """Snapshot a skill directory into <skill-dir>/.drill/snapshots/."""
    skill_dir = _validate_skill_dir(skill_dir)
    inventory = ingest_mod.ingest(skill_dir)
    snap = _write_snapshot(inventory, skill_dir)

    table = Table(title=f"drill ingest — {skill_dir}", show_lines=False)
    table.add_column("Skill", style="cyan")
    table.add_column("Body words", justify="right")
    table.add_column("Files", justify="right")
    table.add_column("Tools", justify="right")
    table.add_column("Notes", style="dim")
    for d in inventory.skills:
        table.add_row(
            d.slug,
            str(d.body_word_count) if d.has_skill_md else "—",
            str(d.file_count) if d.has_skill_md else "—",
            str(len(d.allowed_tools)),
            "; ".join(d.notes) if d.notes else "",
        )
    console.print(table)
    console.print(
        f"[green]✓[/green] {inventory.total_skills} skill(s) · "
        f"layout: {inventory.layout} · snapshot: [bold]{snap}[/bold]"
    )

    if record_version:
        entry = version_mod.record_if_changed(skill_dir, inventory, snap)
        if entry is not None:
            console.print(
                f"[green]✓[/green] version recorded · fp `{entry.inventory_fingerprint[:12]}`"
            )
        else:
            console.print("[dim]inventory unchanged · no new version entry[/dim]")


@app.command("scan")
def cmd_scan(
    skill_dir: Path = typer.Argument(
        ...,
        help="Skill folder or parent directory.",
    ),
    bloat_threshold: int = typer.Option(
        scan_mod.BLOAT_WORD_THRESHOLD, "--bloat-threshold",
        help="SKILL.md body word count above which we flag bloat.",
    ),
    tool_threshold: int = typer.Option(
        scan_mod.TOOL_SPRAWL_THRESHOLD, "--tool-threshold",
        help="allowed-tools count above which we flag tool sprawl.",
    ),
    overlap_threshold: float = typer.Option(
        scan_mod.OVERLAP_JACCARD_THRESHOLD, "--overlap-threshold",
        help="Jaccard similarity above which we flag descriptive overlap.",
    ),
    write: bool = typer.Option(
        True, "--write/--no-write",
        help="Persist scan-<timestamp>.{md,json} under <skill-dir>/.drill/.",
    ),
) -> None:
    """Run deterministic diagnostics over a fresh snapshot."""
    skill_dir = _validate_skill_dir(skill_dir)
    inventory = ingest_mod.ingest(skill_dir)
    report = scan_mod.scan(
        inventory,
        bloat_threshold=bloat_threshold,
        tool_threshold=tool_threshold,
        overlap_threshold=overlap_threshold,
    )

    sev_counts = {"critical": 0, "warn": 0, "info": 0}
    for f in report.findings:
        sev_counts[f.severity] = sev_counts.get(f.severity, 0) + 1

    if not report.findings:
        console.print(Panel(
            "[green]No issues detected.[/green]",
            title=f"drill scan — {skill_dir}",
        ))
    else:
        table = Table(title=f"drill scan — {skill_dir}", show_lines=False)
        table.add_column("Severity", style="bold")
        table.add_column("Kind", style="cyan")
        table.add_column("Skill", style="dim")
        table.add_column("Message")
        for f in report.findings:
            color = {"critical": "red", "warn": "yellow", "info": "blue"}.get(f.severity, "white")
            table.add_row(
                f"[{color}]{f.severity}[/{color}]",
                f.kind,
                f.skill or "—",
                f.message,
            )
        console.print(table)

    console.print(
        f"[green]✓[/green] {len(report.findings)} finding(s) — "
        f"critical: {sev_counts['critical']}, "
        f"warn: {sev_counts['warn']}, "
        f"info: {sev_counts['info']}"
    )

    if write:
        out_path = scan_mod.write_report(report, skill_dir)
        console.print(f"  report: [bold]{out_path}[/bold]")


@app.command("watch")
def cmd_watch(
    skill_dir: Path = typer.Argument(...),
    write: bool = typer.Option(
        True, "--write/--no-write",
        help="Persist watch-<date>.md under <skill-dir>/.drill/.",
    ),
) -> None:
    """Diff the two most recent snapshots and emit evolution findings."""
    skill_dir = _validate_skill_dir(skill_dir)
    snaps = watch_mod.list_snapshots(skill_dir)
    if len(snaps) < 2:
        console.print(
            f"[yellow]Need at least 2 snapshots to watch — found {len(snaps)}.[/yellow]"
        )
        console.print("[dim]Run `drill ingest` at least twice with changes in between.[/dim]")
        raise typer.Exit(code=0)

    report = watch_mod.watch(skill_dir)

    if not report.findings:
        console.print(Panel(
            "[green]No evolution detected.[/green]",
            title=f"drill watch — {skill_dir}",
        ))
    else:
        table = Table(title=f"drill watch — {skill_dir}", show_lines=False)
        table.add_column("Severity", style="bold")
        table.add_column("Kind", style="cyan")
        table.add_column("Skill", style="dim")
        table.add_column("Message")
        for f in report.findings:
            color = {"critical": "red", "warn": "yellow", "info": "blue"}.get(f.severity, "white")
            table.add_row(
                f"[{color}]{f.severity}[/{color}]",
                f.kind,
                f.skill or "—",
                f.message,
            )
        console.print(table)

    console.print(f"[green]✓[/green] {len(report.findings)} finding(s)")

    if write:
        out_path = watch_mod.write_report(report, skill_dir)
        console.print(f"  report: [bold]{out_path}[/bold]")


@app.command("snapshots")
def cmd_snapshots(
    skill_dir: Path = typer.Argument(...),
) -> None:
    """List recorded snapshots, oldest → newest."""
    skill_dir = _validate_skill_dir(skill_dir)
    snaps = watch_mod.list_snapshots(skill_dir)
    if not snaps:
        console.print("[dim]no snapshots recorded yet[/dim]")
        return
    table = Table(title=f"snapshots — {skill_dir}")
    table.add_column("#", justify="right")
    table.add_column("Path")
    for i, p in enumerate(snaps, start=1):
        table.add_row(str(i), str(p))
    console.print(table)


@app.command("version")
def cmd_version(
    skill_dir: Path = typer.Argument(...),
    note: str | None = typer.Option(
        None, "--note",
        help="Annotate the most recent version entry with a free-form note.",
    ),
) -> None:
    """Show the inventory version log (or annotate the latest entry with --note)."""
    skill_dir = _validate_skill_dir(skill_dir)
    if note is not None:
        entry = version_mod.annotate_latest(skill_dir, note)
        if entry is None:
            console.print("[yellow]no versions recorded yet[/yellow]")
            raise typer.Exit(code=0)
        console.print(f"[green]✓[/green] annotated v{len(version_mod.load_versions(skill_dir))}")
        return
    entries = version_mod.load_versions(skill_dir)
    console.print(version_mod.render_log(entries))


def register(parent: typer.Typer) -> None:
    parent.add_typer(app, name="drill")
