"""``agentforge market ...`` sub-CLI (Phase 1.0)."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from agentforge.day2.cli_validators import validate_dir
from agentforge.market.gap import (
    DEFAULT_COVERAGE_ROLE_THRESHOLD,
    compute_gap,
    write_gap_report,
)
from agentforge.market.trends import (
    DEFAULT_RECENCY_WINDOW_DAYS,
    trends_for_directory,
    write_trends_report,
)

app = typer.Typer(
    name="market",
    help="Day-2+ JD-corpus observability: trends, gap (vs an agent's skills).",
    no_args_is_help=True,
)
console = Console()


@app.command("trends")
def cmd_trends(
    jd_folder: Path = typer.Argument(
        ...,
        help="Directory of JD markdown files (one per role).",
    ),
    output_dir: Path | None = typer.Option(
        None, "--output-dir", "-o",
        help="Where to write market-trends.{md,json}. Default: <jd-folder>/.agentforge/market/",
    ),
    model: str | None = typer.Option(
        None, "--model", "-m",
        help="LLM model for per-JD skill extraction.",
    ),
    no_cache: bool = typer.Option(
        False, "--no-cache",
        help="Force re-extraction (ignore cached results).",
    ),
    recency_window_days: int = typer.Option(
        DEFAULT_RECENCY_WINDOW_DAYS, "--recency-window-days",
        help="Days defining the 'recent' bucket for the rising/falling split.",
    ),
    top_n: int = typer.Option(
        25, "--top-n",
        help="Top-N skills to render in the table.",
    ),
) -> None:
    """Aggregate-statistics report over a JD corpus."""
    jd_folder = validate_dir(jd_folder, entity="jd-folder")
    out_dir = (output_dir or (jd_folder / ".agentforge" / "market")).expanduser().resolve()

    from agentforge.llm.client import LLMClient
    client = LLMClient(model=model) if model else LLMClient()

    console.print(Panel(
        f"[cyan]market trends[/cyan] · {jd_folder}\n"
        f"model: [bold]{client.model}[/bold] · cache: {'off' if no_cache else 'on'} · "
        f"recency window: {recency_window_days}d",
        title="market trends",
    ))

    corpus, report = trends_for_directory(
        jd_folder, client=client, use_cache=not no_cache,
        recency_window_days=recency_window_days,
    )

    table = Table(title=f"top {top_n} skills by demand", show_lines=False)
    table.add_column("Skill", style="cyan")
    table.add_column("Roles", justify="right")
    table.add_column("Share", justify="right")
    table.add_column("Category", style="dim")
    table.add_column("Importance (max)")
    for s in report.skills[:top_n]:
        table.add_row(
            s.canonical_name,
            str(s.role_count),
            f"{s.role_share:.0%}",
            s.category or "—",
            s.importance_max or "—",
        )
    console.print(table)

    md_path, json_path = write_trends_report(report, out_dir)
    console.print(
        f"[green]✓[/green] {report.role_count} role(s), "
        f"[bold]{len(report.skills)}[/bold] unique skill clusters."
    )
    console.print(f"  trends md:   [bold]{md_path}[/bold]")
    console.print(f"  trends json: [bold]{json_path}[/bold]")
    if report.recency is not None:
        if report.recency.note:
            console.print(f"  recency:    [dim]{report.recency.note}[/dim]")
        else:
            console.print(
                f"  recency:    rising={len(report.recency.rising)} · "
                f"falling={len(report.recency.falling)}"
            )


@app.command("gap")
def cmd_gap(
    jd_folder: Path = typer.Argument(
        ...,
        help="Directory of JD markdown files (the market).",
    ),
    skill_dir: Path = typer.Option(
        ...,
        "--skill-dir", "-s",
        help="Agent skill directory to compare against (drill-shaped).",
    ),
    output_dir: Path | None = typer.Option(
        None, "--output-dir", "-o",
        help="Where to write market-gap.{md,json}. Default: <skill-dir>/.drill/market/",
    ),
    model: str | None = typer.Option(
        None, "--model", "-m",
        help="LLM model for per-JD skill extraction.",
    ),
    no_cache: bool = typer.Option(
        False, "--no-cache",
        help="Force re-extraction (ignore cached results).",
    ),
    coverage_role_threshold: int = typer.Option(
        DEFAULT_COVERAGE_ROLE_THRESHOLD, "--coverage-role-threshold",
        help="Skills appearing in ≥N roles count as load-bearing for coverage.",
    ),
) -> None:
    """Compare an agent's skill folder to the corpus's demanded skills."""
    jd_folder = validate_dir(jd_folder, entity="jd-folder")
    skill_dir = validate_dir(skill_dir, entity="skill-dir")
    out_dir = (output_dir or (skill_dir / ".drill" / "market")).expanduser().resolve()

    from agentforge.department.cluster import cluster_skills
    from agentforge.department.synthesize import _default_extractor, extract_corpus
    from agentforge.corpus import load_corpus
    from agentforge.drill.ingest import ingest as drill_ingest
    from agentforge.llm.client import LLMClient

    client = LLMClient(model=model) if model else LLMClient()

    console.print(Panel(
        f"[cyan]market gap[/cyan]\n"
        f"market: [bold]{jd_folder}[/bold]\n"
        f"agent:  [bold]{skill_dir}[/bold]\n"
        f"model: [bold]{client.model}[/bold] · cache: {'off' if no_cache else 'on'}",
        title="market gap",
    ))

    corpus = load_corpus(jd_folder)
    extractions = extract_corpus(corpus, _default_extractor(client), use_cache=not no_cache)
    landscape = cluster_skills(extractions)
    inventory = drill_ingest(skill_dir)

    report = compute_gap(
        landscape, inventory,
        coverage_role_threshold=coverage_role_threshold,
        corpus_root=str(jd_folder),
    )

    table = Table(title="gap analysis", show_lines=False)
    table.add_column("Side", style="bold")
    table.add_column("Severity", style="dim")
    table.add_column("Skill")
    table.add_column("Roles", justify="right")

    def _color(sev: str) -> str:
        return {"critical": "red", "warn": "yellow", "info": "blue"}.get(sev, "white")

    for g in report.market_only[:20]:
        table.add_row(
            "market_only",
            f"[{_color(g.severity)}]{g.severity}[/{_color(g.severity)}]",
            g.canonical_name,
            str(g.role_count),
        )
    if len(report.market_only) > 20:
        table.add_row("…", "", f"_{len(report.market_only) - 20} more_", "")
    for g in report.agent_only:
        table.add_row("agent_only", "info", g.canonical_name, "—")
    console.print(table)

    md_path, json_path = write_gap_report(report, out_dir)
    pct = int(round(report.coverage_score * 100))
    console.print(
        f"\n[green]✓[/green] coverage: [bold]{pct}%[/bold] · "
        f"market_only: {len(report.market_only)} · "
        f"agent_only: {len(report.agent_only)} · "
        f"shared: {len(report.shared)}"
    )
    console.print(f"  gap md:   [bold]{md_path}[/bold]")
    console.print(f"  gap json: [bold]{json_path}[/bold]")


def register(parent: typer.Typer) -> None:
    parent.add_typer(app, name="market")
