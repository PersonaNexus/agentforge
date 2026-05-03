"""``agentforge department ...`` sub-CLI (Phase 1.0)."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from agentforge.corpus import load_corpus
from agentforge.department.synthesize import (
    analyze_directory,
    write_report,
)

app = typer.Typer(
    name="department",
    help="Synthesize a multi-agent team from a JD corpus directory.",
    no_args_is_help=True,
)
console = Console()


@app.command("scan")
def cmd_scan(
    jd_folder: Path = typer.Argument(
        ...,
        help="Directory of JD markdown files (one per role, with YAML frontmatter).",
    ),
) -> None:
    """List the corpus without extracting anything (cheap, no LLM)."""
    jd_folder = jd_folder.expanduser().resolve()
    corpus = load_corpus(jd_folder)
    table = Table(title=f"corpus: {corpus.root}", show_lines=False)
    table.add_column("Role ID", style="cyan")
    table.add_column("Title")
    table.add_column("Seniority", style="dim")
    table.add_column("Body lines", justify="right")
    for e in corpus:
        body_lines = e.body.count("\n")
        table.add_row(
            e.role_id,
            e.title,
            e.frontmatter.seniority or "—",
            str(body_lines),
        )
    console.print(table)
    console.print(f"[green]✓[/green] {len(corpus)} JD(s) loaded")


@app.command("analyze")
def cmd_analyze(
    jd_folder: Path = typer.Argument(
        ...,
        help="Directory of JD markdown files.",
    ),
    output_dir: Path | None = typer.Option(
        None, "--output-dir", "-d",
        help="Where to write skill-landscape.{md,json}. Default: <jd-folder>/.agentforge/",
    ),
    model: str | None = typer.Option(
        None, "--model", "-m",
        help="LLM model for skill extraction.",
    ),
    no_cache: bool = typer.Option(
        False, "--no-cache",
        help="Force re-extraction (ignore cached results in <corpus>/.agentforge/extractions/).",
    ),
) -> None:
    """Phase 1.0: extract skills per role, cluster across roles, write report."""
    jd_folder = jd_folder.expanduser().resolve()
    out_dir = (output_dir or (jd_folder / ".agentforge")).expanduser().resolve()

    from agentforge.llm.client import LLMClient
    client = LLMClient(model=model) if model else LLMClient()
    model_label = client.model

    console.print(Panel(
        f"[cyan]analyzing[/cyan] {jd_folder}\n"
        f"model: [bold]{model_label}[/bold] · "
        f"cache: {'off' if no_cache else 'on'}",
        title="department analyze",
    ))

    corpus, extractions, landscape = analyze_directory(
        jd_folder,
        client=client,
        use_cache=not no_cache,
    )
    md_path, json_path = write_report(corpus, extractions, landscape, out_dir)

    shared = landscape.shared_clusters
    role_spec = landscape.role_specific_clusters
    console.print(
        f"\n[green]✓[/green] {landscape.role_count} role(s), "
        f"[bold]{len(shared)}[/bold] shared skills, "
        f"[bold]{len(role_spec)}[/bold] role-specific."
    )
    console.print(f"  report: [bold]{md_path}[/bold]")
    console.print(f"  json:   [bold]{json_path}[/bold]")


def register(parent: typer.Typer) -> None:
    parent.add_typer(app, name="department")
